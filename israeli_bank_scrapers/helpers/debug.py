"""Port of src/helpers/debug.ts

The JS lib uses the `debug` npm package (enabled via the DEBUG env var). This
uses Python's standard `logging` module instead — enable with:

    import logging
    logging.basicConfig(level=logging.DEBUG)
"""

import logging


def get_debug(name: str) -> logging.Logger:
    return logging.getLogger(f"israeli_bank_scrapers.{name}")
