#!/usr/bin/env python3
"""
strompriser.py — DK1 spot prices from Energi Data Service
Usage:
  python strompriser.py          # today
  python strompriser.py tomorrow # today + tomorrow
"""

import sys
import json
import urllib.request
import urllib.parse
from collections import defaultdict
from datetime import date, timedelta, datetime

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"

MOMS = 0.25  # spot fra API er ekskl. moms; NRGI-tariffer er inkl. moms

# NRGI samlede afgifter pr. time (inkl. elafgift og moms)
TARIFFS = [0.21] * 6 + [0.34] * 11 + [0.70] * 4 + [0.34] * 3


def fetch_prices(start: date, end: date) -> list[dict]:
    end_str = (end + timedelta(days=1)).isoformat()
    filter_param = urllib.parse.quote('{"PriceArea":"DK1"}')
    url = (
        f"https://api.energidataservice.dk/dataset/DayAheadPrices"
        f"?start={start.isoformat()}&end={end_str}"
        f"&filter={filter_param}"
    )
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())
    return data.get("records", [])


def spot_dkk(dkk_mwh) -> float:
    return 0.0 if dkk_mwh is None else dkk_mwh / 1000


def med_afgifter(spot: float, hour: int) -> float:
    return spot * (1 + MOMS) + TARIFFS[hour]


def price_color(p: float, lo: float, hi: float) -> str:
    if hi == lo:
        return GREEN
    t = (p - lo) / (hi - lo)
    if t < 0.33:
        return GREEN
    if t < 0.66:
        return YELLOW
    return RED


def bar(p: float, lo: float, hi: float, width: int = 14) -> str:
    filled = width if hi == lo else round((p - lo) / (hi - lo) * width)
    return "█" * filled + DIM + "░" * (width - filled) + RESET


def aggregate_hourly_prices(records: list[dict]) -> list[tuple[int, float]]:
    buckets: dict[int, list[float]] = defaultdict(list)
    for r in records:
        hour = int(r["TimeDK"][11:13])
        buckets[hour].append(spot_dkk(r["DayAheadPriceDKK"]))
    return [(h, sum(v) / len(v)) for h, v in sorted(buckets.items())]


def format_dkk_price(p: float) -> str:
    return f"{p:.2f} kr"


def get_records_for_date(records: list[dict], date: date) -> list[dict]:
    prefix = date.isoformat()
    return [r for r in records if r["TimeDK"].startswith(prefix)]


def print_day(records: list[dict], label: str, is_today: bool = True):
    if not records:
        print(f"\n{DIM}  Ingen data for {label}{RESET}")
        return

    hourly = aggregate_hourly_prices(records)
    spot_prices = [p * (1 + MOMS) for _, p in hourly]
    total_prices = [med_afgifter(p, hour) for hour, p in hourly]
    lo, hi = min(total_prices), max(total_prices)
    avg_spot = sum(spot_prices) / len(spot_prices)
    avg_total = sum(total_prices) / len(total_prices)
    current_hour = datetime.now().hour

    print(f"\n{BOLD}{CYAN}{'─' * 62}{RESET}")
    print(f"{BOLD}{CYAN}  {label.upper():<30}  DK1 · kr/kWh{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 62}{RESET}")
    print(f"  {DIM}{'':6}{'min':>7}  {'avg':>7}  {'max':>7}{RESET}")
    print(f"  {DIM}spot:  {RESET}{GREEN}{format_dkk_price(min(spot_prices)):>7}{RESET}  {YELLOW}{format_dkk_price(avg_spot):>7}{RESET}  {RED}{format_dkk_price(max(spot_prices)):>7}{RESET}")
    print(f"  {DIM}total: {RESET}{GREEN}{format_dkk_price(lo):>7}{RESET}  {YELLOW}{format_dkk_price(avg_total):>7}{RESET}  {RED}{format_dkk_price(hi):>7}{RESET}")
    print(f"{DIM}{'─' * 62}{RESET}")

    for (hour, p), total in zip(hourly, total_prices):
        color    = price_color(total, lo, hi)
        is_now   = hour == current_hour and is_today
        marker   = f"{BOLD} {RESET}" if is_now else " "
        row_bold = BOLD if is_now else ""
        print(
            f"  {row_bold}{DIM}{hour:02d}:00{RESET}  "
            f"{color}{bar(total, lo, hi)}{RESET}  "
            f"{row_bold}{format_dkk_price(p):>7}  {DIM}→{RESET}  "
            f"{row_bold}{color}{format_dkk_price(total):>7}{RESET} {marker}"
        )

    print(f"{DIM}{'─' * 62}{RESET}")


def main():
    show_tomorrow = len(sys.argv) > 1 and sys.argv[1].lower() in ("tomorrow", "all")
    today = date.today()
    tomorrow   = today + timedelta(days=1) if show_tomorrow else today

    print(f"\n{BOLD}Strømpris · Vestdanmark (DK1){RESET}")
    print(f"{DIM}Kilde: Energi Data Service")

    try:
        records = fetch_prices(today, tomorrow)
    except Exception as e:
        print(f"\n{RED}Fejl: {e}{RESET}")
        sys.exit(1)

    print_day(get_records_for_date(records, today), "I dag")

    if show_tomorrow:
        print_day(get_records_for_date(records, tomorrow), "I morgen", False)

    print()


if __name__ == "__main__":
    main()
