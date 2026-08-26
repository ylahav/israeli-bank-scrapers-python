// Dart client for the israeli-bank-scrapers CLI (see ../israeli_bank_scrapers/cli.py
// for the exact protocol this speaks). Copy this file into your Flutter app's
// lib/ tree and adjust `_executablePath` to wherever you bundle the built
// executable (see ../build/build.py and FLUTTER_INTEGRATION.md).
//
// Usage:
//   final service = BankScraperService(executablePath: myBundledExePath);
//   final stream = service.scrape(
//     companyId: 'leumi',
//     credentials: {'username': user, 'password': pass},
//     startDate: DateTime.now().subtract(const Duration(days: 90)),
//   );
//   await for (final event in stream) {
//     switch (event) {
//       case ScrapeProgress p:
//         print('progress: ${p.progress}');
//       case ScrapeSuccess s:
//         print('got ${s.accounts.length} accounts');
//       case ScrapeFailure f:
//         print('failed: ${f.errorType} ${f.errorMessage}');
//     }
//   }

import 'dart:async';
import 'dart:convert';
import 'dart:io';

/// One JSON line emitted by the CLI, parsed into a typed event.
sealed class ScrapeEvent {}

class ScrapeProgress extends ScrapeEvent {
  final String companyId;
  final String progress; // one of the ScraperProgressTypes values, e.g. "LOGGING_IN"
  ScrapeProgress(this.companyId, this.progress);
}

class ScrapeSuccess extends ScrapeEvent {
  final List<Map<String, dynamic>> accounts; // raw account dicts — see note below on typed models
  ScrapeSuccess(this.accounts);
}

class ScrapeFailure extends ScrapeEvent {
  final String? errorType;
  final String? errorMessage;
  ScrapeFailure(this.errorType, this.errorMessage);
}

/// Thrown when the CLI process itself couldn't be started or crashed before
/// emitting any protocol line at all (missing executable, permissions, etc.)
/// — distinct from ScrapeFailure, which is a clean, expected failure the
/// scraper itself reported (bad credentials, site changed, etc.).
class ScraperProcessException implements Exception {
  final String message;
  ScraperProcessException(this.message);
  @override
  String toString() => 'ScraperProcessException: $message';
}

class BankScraperService {
  final String executablePath;

  BankScraperService({required this.executablePath});

  /// Runs one scrape and streams progress events, ending with exactly one
  /// ScrapeSuccess or ScrapeFailure. The stream closes after that final event.
  Stream<ScrapeEvent> scrape({
    required String companyId,
    required Map<String, String> credentials,
    DateTime? startDate,
    Map<String, dynamic>? options,
  }) {
    final controller = StreamController<ScrapeEvent>();

    () async {
      Process? process;
      try {
        process = await Process.start(executablePath, []);
      } catch (e) {
        controller.addError(ScraperProcessException('failed to start CLI process: $e'));
        await controller.close();
        return;
      }

      final request = <String, dynamic>{
        'company_id': companyId,
        'credentials': credentials,
        if (startDate != null) 'start_date': _isoDate(startDate),
        if (options != null) 'options': options,
      };

      process.stdin.write(jsonEncode(request));
      await process.stdin.close();

      // Surface stderr for debugging (tracebacks, playwright logs) without
      // treating it as a protocol channel — only stdout lines are parsed.
      process.stderr.transform(utf8.decoder).listen((chunk) {
        if (chunk.trim().isNotEmpty) {
          // ignore: avoid_print
          print('[bank-scraper-cli stderr] $chunk');
        }
      });

      var sawTerminalEvent = false;

      await for (final line in process.stdout.transform(utf8.decoder).transform(const LineSplitter())) {
        if (line.trim().isEmpty) continue;

        late final Map<String, dynamic> obj;
        try {
          obj = jsonDecode(line) as Map<String, dynamic>;
        } catch (e) {
          controller.addError(ScraperProcessException('non-JSON line from CLI: $line'));
          continue;
        }

        switch (obj['type']) {
          case 'progress':
            controller.add(ScrapeProgress(obj['company_id'] as String, obj['progress'] as String));
          case 'result':
            sawTerminalEvent = true;
            if (obj['success'] == true) {
              final accounts = (obj['accounts'] as List<dynamic>? ?? [])
                  .cast<Map<String, dynamic>>();
              controller.add(ScrapeSuccess(accounts));
            } else {
              controller.add(ScrapeFailure(obj['error_type'] as String?, obj['error_message'] as String?));
            }
          case 'fatal_error':
            sawTerminalEvent = true;
            controller.add(ScrapeFailure('FATAL', obj['message'] as String?));
          default:
            // Unknown event type — forward compatibility: ignore rather than crash.
            break;
        }
      }

      final exitCode = await process.exitCode;
      if (!sawTerminalEvent) {
        controller.addError(
          ScraperProcessException('CLI process exited (code $exitCode) without emitting a result'),
        );
      }

      await controller.close();
    }();

    return controller.stream;
  }

  String _isoDate(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
}
