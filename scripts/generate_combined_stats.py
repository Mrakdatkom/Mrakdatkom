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

    background = "#0a0a0a"
    line = "#2a2a2a"
    text = "#fafafa"
    muted = "#8a8a8a"
    accent = "#c6ff3d"

    # Single-hue ramp: empty -> dark olive -> lime
    heat = [
        "#17181b",
        "#2f3d10",
        "#587a14",
        "#8fc21f",
        accent,
    ]

    font = "'Helvetica Neue', Helvetica, Arial, sans-serif"

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

    def label(x, y, content, fill=muted, anchor="start", size=12):
        return (
            f'<text x="{x}" y="{y}" fill="{fill}" '
            f'text-anchor="{anchor}" '
            f'font-family="{font}" font-size="{size}" '
            f'font-weight="600" letter-spacing="2.5">'
            f'{escape(content.upper())}'
            f'</text>'
        )

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',

        f'<rect width="100%" height="100%" '
        f'rx="18" fill="{background}"/>',

        f'<rect x="1" y="1" '
        f'width="{width - 2}" height="{height - 2}" '
        f'rx="18" fill="none" stroke="{line}"/>',

        # Header row
        label(68, 50, "Combined GitHub Activity", text),

        f'<line x1="48" y1="72" x2="1052" y2="72" stroke="{line}"/>',

        # Hero number
        f'<text x="44" y="190" fill="{text}" '
        f'font-family="{font}" font-size="124" '
        f'font-weight="800" letter-spacing="-5">'
        f'{escape(combined_total)}'
        f'</text>',

        label(48, 226, "Contributions, combined", accent),

        # Vertical dividers for the supporting stats
        f'<line x1="496" y1="100" x2="496" y2="226" stroke="{line}"/>',
        f'<line x1="676" y1="100" x2="676" y2="226" stroke="{line}"/>',
        f'<line x1="856" y1="100" x2="856" y2="226" stroke="{line}"/>',
    ]

    stats = [
        ("dvmark3", primary_total, 520, text),
        ("markryan3421", secondary_total, 700, text),
        ("Current streak", f"{current_streak} days", 880, accent),
    ]

    for name, value, x, value_fill in stats:
        svg.extend([
            f'<text x="{x}" y="176" fill="{value_fill}" '
            f'font-family="{font}" font-size="42" '
            f'font-weight="800" letter-spacing="-1">'
            f'{escape(value)}'
            f'</text>',

            label(x, 204, name),
        ])

    svg.extend([
        f'<line x1="48" y1="256" x2="1052" y2="256" stroke="{line}"/>',
        label(48, 290, "Last 52 weeks"),
    ])

    gap = 4
    columns = 52
    grid_width = 1004  # x=48 to x=1052
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

        svg.append(
            f'<rect x="{x}" y="{y}" '
            f'width="{cell_size}" '
            f'height="{cell_size}" '
            f'rx="2" fill="{heat[level(count)]}">'
            f'<title>'
            f'{escape(current_day.isoformat())}: '
            f'{count} contributions'
            f'</title>'
            f'</rect>'
        )

        current_day += dt.timedelta(days=1)

    # Footer: caption on the left, Less/More legend on the right
    svg.append(label(48, 475, "Both accounts, merged"))

    svg.append(label(926, 475, "Less", muted, "end"))

    for i, color in enumerate(heat):
        svg.append(
            f'<rect x="{936 + i * 16}" y="465" '
            f'width="12" height="12" rx="2" fill="{color}"/>'
        )
        
    svg.append(label(1052, 475, "  More", muted, "end"))

    svg.append('</svg>')

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
