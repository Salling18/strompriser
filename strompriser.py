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
    # Build URL manually — urlencode double-encodes the JSON filter and causes 400s
    days = (end - start).days + 1
    end_str = (end + timedelta(days=1)).isoformat()
    url = (
        f"https://api.energidataservice.dk/dataset/DayAheadPrices"
        f"?start={start.isoformat()}&end={end_str}"
        f"&filter={_FILTER}&sort={_SORT}&limit={days * 96}"
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


def aggregate_hourly(records: list[dict]) -> list[tuple[int, float]]:
    """Aggregate 15-min DayAheadPrices records into hourly (hour, DKK/kWh) pairs."""
    buckets: dict[int, list[float]] = defaultdict(list)
    for r in records:
        hour = int(r["TimeDK"][11:13])
        buckets[hour].append(spot_dkk(r["DayAheadPriceDKK"]))
    return [(h, sum(v) / len(v)) for h, v in sorted(buckets.items())]


def fmt(p: float) -> str:
    return f"{p:.2f} kr"


def records_for(records: list[dict], d: date) -> list[dict]:
    prefix = d.isoformat()
    return [r for r in records if r["TimeDK"].startswith(prefix)]


def print_day(records: list[dict], label: str, is_today: bool = False):
    if not records:
        print(f"\n{DIM}  Ingen data for {label}{RESET}")
        return

    hourly = aggregate_hourly(records)
    spot_prices = [p * (1 + MOMS) for _, p in hourly]
    total_prices = [med_afgifter(p, hour) for hour, p in hourly]
    lo, hi = min(total_prices), max(total_prices)
    avg_spot  = sum(spot_prices) / len(spot_prices)
    avg_total = sum(total_prices) / len(total_prices)
    now_hour  = datetime.now().hour if is_today else -1

    print(f"\n{BOLD}{CYAN}{'─' * 62}{RESET}")
    print(f"{BOLD}{CYAN}  {label.upper():<30}  DK1 · kr/kWh{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 62}{RESET}")
    print(f"  {DIM}{'':6}{'min':>7}  {'avg':>7}  {'max':>7}{RESET}")
    print(f"  {DIM}spot:  {RESET}{GREEN}{fmt(min(spot_prices)):>7}{RESET}  {YELLOW}{fmt(avg_spot):>7}{RESET}  {RED}{fmt(max(spot_prices)):>7}{RESET}")
    print(f"  {DIM}total: {RESET}{GREEN}{fmt(lo):>7}{RESET}  {YELLOW}{fmt(avg_total):>7}{RESET}  {RED}{fmt(hi):>7}{RESET}")
    print(f"{DIM}{'─' * 62}{RESET}")

    for (hour, p), total in zip(hourly, total_prices):
        color    = price_color(total, lo, hi)
        is_now   = hour == now_hour
        marker   = f"{BOLD} {RESET}" if is_now else " "
        row_bold = BOLD if is_now else ""
        print(
            f"  {row_bold}{DIM}{hour:02d}:00{RESET}  "
            f"{color}{bar(total, lo, hi)}{RESET}  "
            f"{row_bold}{fmt(p):>7}  {DIM}→{RESET}  "
            f"{row_bold}{color}{fmt(total):>7}{RESET} {marker}"
        )

    print(f"{DIM}{'─' * 62}{RESET}")


def main():
    show_tomorrow = len(sys.argv) > 1 and sys.argv[1].lower() in ("tomorrow", "all")

    today = date.today()
    tomorrow   = today + timedelta(days=1) if show_tomorrow else today

    print(f"\n{BOLD}Strømpris · Vestdanmark (DK1){RESET}")
    print(f"{DIM}Kilde: Energi Data Service · alle priser inkl. moms{RESET}")

    try:
        records = fetch_prices(today, tomorrow)
    except Exception as e:
        print(f"\n{RED}Fejl: {e}{RESET}")
        sys.exit(1)

    print_day(records_for(records, today), "I dag", is_today=True)

    if show_tomorrow:
        print_day(records_for(records, tomorrow), "I morgen")

    print()


if __name__ == "__main__":
    main()
