import datetime as dt
import html
import os
from pathlib import Path

import requests


API_URL = "https://api.github.com/graphql"

USERS = [
    "dvmark3",
    "markryan3421",
]

OUTPUT = Path("assets/combined-github-stats.svg")


def github_graphql(token, query, variables):
    response = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "query": query,
            "variables": variables,
        },
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if "errors" in data:
        raise RuntimeError(data["errors"])

    return data["data"]


def get_account_created_at(token, username):
    query = """
    query($login: String!) {
        user(login: $login) {
            createdAt
        }
    }
    """

    data = github_graphql(
        token,
        query,
        {"login": username},
    )

    created_at = data["user"]["createdAt"]

    return dt.datetime.fromisoformat(
        created_at.replace("Z", "+00:00")
    ).date()


def get_contributions(token, username, start_date, end_date):
    query = """
    query(
        $login: String!,
        $from: DateTime!,
        $to: DateTime!
    ) {
        user(login: $login) {
            contributionsCollection(
                from: $from,
                to: $to
            ) {
                contributionCalendar {
                    totalContributions

                    weeks {
                        contributionDays {
                            date
                            contributionCount
                        }
                    }
                }
            }
        }
    }
    """

    variables = {
        "login": username,
        "from": f"{start_date.isoformat()}T00:00:00Z",
        "to": f"{end_date.isoformat()}T23:59:59Z",
    }

    data = github_graphql(
        token,
        query,
        variables,
    )

    calendar = (
        data["user"]
        ["contributionsCollection"]
        ["contributionCalendar"]
    )

    days = {}

    for week in calendar["weeks"]:
        for day in week["contributionDays"]:
            days[day["date"]] = int(
                day["contributionCount"]
            )

    return calendar["totalContributions"], days


def collect_account(token, username):
    today = dt.datetime.now(
        dt.timezone.utc
    ).date()

    created = get_account_created_at(
        token,
        username,
    )

    current = created
    total = 0
    days = {}

    while current <= today:
        end = min(
            current + dt.timedelta(days=364),
            today,
        )

        chunk_total, chunk_days = get_contributions(
            token,
            username,
            current,
            end,
        )

        total += chunk_total

        for date, count in chunk_days.items():
            days[date] = count

        current = end + dt.timedelta(days=1)

    return total, days


def calculate_streaks(days):
    active_days = {
        dt.date.fromisoformat(date)
        for date, count in days.items()
        if count > 0
    }

    if not active_days:
        return 0, 0

    ordered = sorted(active_days)

    longest = 1
    current_run = 1

    for previous, current in zip(
        ordered,
        ordered[1:],
    ):
        if current == previous + dt.timedelta(days=1):
            current_run += 1
            longest = max(
                longest,
                current_run,
            )
        else:
            current_run = 1

    today = dt.datetime.now(
        dt.timezone.utc
    ).date()

    current_streak = 0
    cursor = today

    while cursor in active_days:
        current_streak += 1
        cursor -= dt.timedelta(days=1)

    return current_streak, longest


def escape(value):
    return html.escape(
        str(value),
        quote=True,
    )


def render_svg(
    primary_total,
    secondary_total,
    combined_total,
    days,
    current_streak,
    longest_streak,
):
    today = dt.datetime.now(
        dt.timezone.utc
    ).date()

    start = today - dt.timedelta(days=364)

    width = 1100
    height = 500

    text = "#f8fafc"
    muted = "#94a3b8"

    # Heatmap ramp: empty -> teal -> green
    heat = [
        "#1a2238",
        "#0f4c5c",
        "#0e7c86",
        "#14b8a6",
        "#4ade80",
    ]

    dates = [
        start + dt.timedelta(days=i)
        for i in range(365)
    ]

    max_count = max(
        [
            days.get(
                date.isoformat(),
                0,
            )
            for date in dates
        ]
        + [1]
    )

    def level(count):
        if count <= 0:
            return 0

        ratio = count / max_count

        if ratio <= 0.25:
            return 1

        if ratio <= 0.50:
            return 2

        if ratio <= 0.75:
            return 3

        return 4

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',

        '<defs>',

        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#070b1a"/>'
        '<stop offset="0.55" stop-color="#0d1030"/>'
        '<stop offset="1" stop-color="#08202b"/>'
        '</linearGradient>',

        '<linearGradient id="edge" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#2dd4bf" stop-opacity="0.75"/>'
        '<stop offset="0.5" stop-color="#818cf8" stop-opacity="0.35"/>'
        '<stop offset="1" stop-color="#4ade80" stop-opacity="0.75"/>'
        '</linearGradient>',

        '<linearGradient id="title" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="#ffffff"/>'
        '<stop offset="0.6" stop-color="#a5f3fc"/>'
        '<stop offset="1" stop-color="#c4b5fd"/>'
        '</linearGradient>',

        '<linearGradient id="num" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#ffffff"/>'
        '<stop offset="1" stop-color="#99f6e4"/>'
        '</linearGradient>',

        '<linearGradient id="streak" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#4ade80"/>'
        '<stop offset="1" stop-color="#2dd4bf"/>'
        '</linearGradient>',

        '<filter id="blur" x="-50%" y="-50%" '
        'width="200%" height="200%">'
        '<feGaussianBlur stdDeviation="60"/>'
        '</filter>',

        '<filter id="glow" x="-100%" y="-100%" '
        'width="300%" height="300%">'
        '<feGaussianBlur stdDeviation="2.5" result="b"/>'
        '<feMerge>'
        '<feMergeNode in="b"/>'
        '<feMergeNode in="SourceGraphic"/>'
        '</feMerge>'
        '</filter>',

        f'<clipPath id="card">'
        f'<rect width="{width}" height="{height}" rx="18"/>'
        f'</clipPath>',

        '</defs>',

        # Background + aurora glows, clipped to the rounded card
        '<g clip-path="url(#card)">',
        f'<rect width="{width}" height="{height}" fill="url(#bg)"/>',
        '<circle cx="140" cy="40" r="220" fill="#14b8a6" '
        'opacity="0.28" filter="url(#blur)"/>',
        '<circle cx="980" cy="120" r="240" fill="#6366f1" '
        'opacity="0.30" filter="url(#blur)"/>',
        '<circle cx="620" cy="480" r="260" fill="#22c55e" '
        'opacity="0.16" filter="url(#blur)"/>',
        '</g>',

        # Card border
        f'<rect x="1" y="1" '
        f'width="{width - 2}" height="{height - 2}" '
        f'rx="18" fill="none" stroke="url(#edge)" '
        f'stroke-opacity="0.6"/>',

        # Title
        f'<text x="46" y="55" fill="url(#title)" '
        f'font-family="Arial, Helvetica, sans-serif" '
        f'font-size="28" font-weight="700">'
        f'Combined GitHub Activity'
        f'</text>',

        f'<text x="46" y="82" fill="{muted}" '
        f'font-family="Arial, Helvetica, sans-serif" '
        f'font-size="15">'
        f'@dvmark3 + @markryan3421'
        f'</text>',

        # Frosted glass panel
        '<rect x="46" y="110" width="1008" height="150" '
        'rx="14" fill="#ffffff" fill-opacity="0.06" '
        'stroke="url(#edge)" stroke-width="1.2"/>',

        # Top highlight for the glass effect
        '<line x1="62" y1="111" x2="1038" y2="111" '
        'stroke="#ffffff" stroke-opacity="0.18"/>',

        # Soft dividers between stats
        '<line x1="298" y1="140" x2="298" y2="230" '
        'stroke="#ffffff" stroke-opacity="0.08"/>',
        '<line x1="550" y1="140" x2="550" y2="230" '
        'stroke="#ffffff" stroke-opacity="0.08"/>',
        '<line x1="803" y1="140" x2="803" y2="230" '
        'stroke="#ffffff" stroke-opacity="0.08"/>',
    ]

    stats = [
        ("Combined Contributions", combined_total, 172, "url(#num)"),
        ("dvmark3", primary_total, 424, "url(#num)"),
        ("markryan3421", secondary_total, 676, "url(#num)"),
        ("Current Streak", current_streak, 930, "url(#streak)"),
    ]

    for label, value, x, value_fill in stats:
        suffix = (
            " days"
            if label == "Current Streak"
            else ""
        )

        svg.extend([
            f'<text x="{x}" y="185" '
            f'text-anchor="middle" '
            f'fill="{value_fill}" '
            f'font-family="Arial, Helvetica, sans-serif" '
            f'font-size="32" font-weight="700">'
            f'{escape(value)}{suffix}'
            f'</text>',

            f'<text x="{x}" y="218" '
            f'text-anchor="middle" '
            f'fill="{muted}" '
            f'font-family="Arial, Helvetica, sans-serif" '
            f'font-size="14">'
            f'{escape(label)}'
            f'</text>',
        ])

    gap = 4
    columns = 52
    grid_width = 1004  # x=48 to x=1052, inside the panel (46 to 1054)
    cell_size = round((grid_width - (columns - 1) * gap) / columns, 2)

    days_since_sunday = (today.weekday() + 1) % 7
    first_day = today - dt.timedelta(
        days=days_since_sunday + (columns - 1) * 7
    )

    current_day = first_day

    while current_day <= today:
        offset = (
            current_day - first_day
        ).days

        week = offset // 7
        weekday = offset % 7

        x = 48 + week * (
            cell_size + gap
        )

        y = 312 + weekday * (
            cell_size + gap
        )

        if (
            start <= current_day <= today
        ):
            count = days.get(
                current_day.isoformat(),
                0,
            )
        else:
            count = 0

        lvl = level(count)
        glow = ' filter="url(#glow)"' if lvl >= 3 else ""

        svg.append(
            f'<rect x="{x}" y="{y}" '
            f'width="{cell_size}" '
            f'height="{cell_size}" '
            f'rx="3" fill="{heat[lvl]}"{glow}>'
            f'<title>'
            f'{escape(current_day.isoformat())}: '
            f'{count} contributions'
            f'</title>'
            f'</rect>'
        )

        current_day += dt.timedelta(days=1)

    svg.extend([
        f'<text x="48" y="475" '
        f'fill="{muted}" '
        f'font-family="Arial, Helvetica, sans-serif" '
        f'font-size="13">'
        f'Combined activity from both GitHub accounts'
        f'</text>',
        '</svg>',
    ])

    return "\n".join(svg)


def main():
    token = os.getenv("GH_STATS_TOKEN")

    if not token:
        raise SystemExit(
            "GH_STATS_TOKEN is missing."
        )

    account_totals = {}
    combined_days = {}

    for username in USERS:
        total, days = collect_account(
            token,
            username,
        )

        account_totals[username] = total

        for date, count in days.items():
            combined_days[date] = (
                combined_days.get(date, 0)
                + count
            )

    primary_total = account_totals[
        "dvmark3"
    ]

    secondary_total = account_totals[
        "markryan3421"
    ]

    combined_total = (
        primary_total
        + secondary_total
    )

    current_streak, longest_streak = (
        calculate_streaks(
            combined_days
        )
    )

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT.write_text(
        render_svg(
            primary_total,
            secondary_total,
            combined_total,
            combined_days,
            current_streak,
            longest_streak,
        ),
        encoding="utf-8",
    )

    print(
        "Combined GitHub statistics:"
    )

    print(
        f"dvmark3: {primary_total}"
    )

    print(
        f"markryan3421: {secondary_total}"
    )

    print(
        f"Combined: {combined_total}"
    )

    print(
        f"Current streak: {current_streak}"
    )

    print(
        f"Longest streak: {longest_streak}"
    )


if __name__ == "__main__":
    main()
