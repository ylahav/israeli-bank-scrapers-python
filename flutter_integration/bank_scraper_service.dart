// Dart client for the israeli-bank-scrapers CLI (see ../israeli_bank_scrapers/cli.py
// for the exact protocol this speaks — schema_version 2). Copy this file into
// your Flutter app's lib/ tree and adjust `_executablePath` to wherever you
// bundle the built executable (see ../build/build.py and FLUTTER_INTEGRATION.md).
//
// Usage (no OTP needed — most companies):
//   final service = BankScraperService(executablePath: myBundledExePath);
//
//   // Check which build you're running (optional, fast, no browser launched):
//   final version = await service.getVersion();
//
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
//       case ScrapeOtpRequired o:
//         // e.g. some insurance companies text/email a one-time code mid-login
//         final code = await promptUserForCode(o.context); // your own UI
//         o.submit(code);
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

/// The scraper's login hit a "type in the code we texted/emailed you" step —
/// call [submit] with the code once your UI has it. `context` always
/// includes `company_id` and may include scraper-specific hints (e.g. a
/// phone number suffix) worth showing the user. The underlying CLI process
/// blocks until you call [submit] — there's no timeout enforced here, so if
/// your UI can be abandoned, consider adding your own.
class ScrapeOtpRequired extends ScrapeEvent {
  final Map<String, dynamic> context;
  final void Function(String code) submit;
  ScrapeOtpRequired(this.context, this.submit);
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
  /// Zero or more ScrapeOtpRequired events may occur before that, for
  /// scrapers whose login needs a one-time code mid-flow.
  Stream<ScrapeEvent> scrape({
    required String companyId,
    required Map<String, String> credentials,
    DateTime? startDate,
    Map<String, dynamic>? options,
  }) {
    final controller = StreamController<ScrapeEvent>();

    () async {
      Process? maybeProcess;
      try {
        maybeProcess = await Process.start(executablePath, []);
      } catch (e) {
        controller.addError(ScraperProcessException('failed to start CLI process: $e'));
        await controller.close();
        return;
      }
      final process = maybeProcess; // non-null from here on — start succeeded above

      final request = <String, dynamic>{
        'company_id': companyId,
        'credentials': credentials,
        if (startDate != null) 'start_date': _isoDate(startDate),
        if (options != null) 'options': options,
      };

      // A single line, newline-terminated — the CLI reads exactly one line
      // as the request. Deliberately NOT closing stdin here: some scrapers
      // need a second line later (the OTP code response), so stdin stays
      // open until the terminal event (result/fatal_error) arrives below.
      process.stdin.write('${jsonEncode(request)}\n');

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
          case 'otp_required':
            final context = (obj['context'] as Map<String, dynamic>?) ?? {};
            controller.add(ScrapeOtpRequired(context, (String code) {
              process.stdin.write('${jsonEncode({'type': 'otp_code', 'code': code})}\n');
            }));
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

      // Now that stdout has closed (the process is done producing protocol
      // lines), close stdin too — safe even if we never needed the OTP
      // round-trip, and required cleanup if we did.
      await process.stdin.close();

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

  /// Queries the version of the bundled CLI executable — useful for
  /// sanity-checking which build a user's app is actually running,
  /// independent of any scrape. This is a fast, one-shot request/response
  /// (not a stream like [scrape]): the CLI answers with a single line and
  /// exits immediately, without launching a browser at all.
  Future<String> getVersion() async {
    Process process;
    try {
      process = await Process.start(executablePath, []);
    } catch (e) {
      throw ScraperProcessException('failed to start CLI process: $e');
    }

    process.stdin.write('${jsonEncode({'type': 'version'})}\n');
    await process.stdin.close();

    final lines = await process.stdout
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .where((line) => line.trim().isNotEmpty)
        .toList();

    final exitCode = await process.exitCode;

    if (lines.isEmpty) {
      throw ScraperProcessException(
        'CLI process exited (code $exitCode) without emitting a version line',
      );
    }

    final Map<String, dynamic> obj;
    try {
      obj = jsonDecode(lines.first) as Map<String, dynamic>;
    } catch (e) {
      throw ScraperProcessException('non-JSON line from CLI: ${lines.first}');
    }

    final version = obj['version'];
    if (obj['type'] != 'version' || version is! String) {
      throw ScraperProcessException('unexpected response to version request: ${lines.first}');
    }

    return version;
  }

  String _isoDate(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
}
