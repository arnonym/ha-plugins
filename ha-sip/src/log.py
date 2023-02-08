from datetime import datetime
from typing import Optional


def log(account_number: Optional[int], message: str) -> None:
    time_stamp = datetime.now()
    time_stamp_str = time_stamp.strftime("%H:%M:%S.%f")
    account_number_str = " " if account_number is None else account_number
    print("| %s [%s] %s" % (time_stamp_str, account_number_str, message))
