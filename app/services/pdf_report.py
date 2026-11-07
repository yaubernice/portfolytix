"""Readable portfolio PDF report for account export."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.schemas.analytics import AnalyticsOut
from app.schemas.planning import GoalOut
from app.schemas.position import PositionsResponse


def _money(value: Decimal | None) -> str:
    if value is None:
        return "—"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def _pct(value: Decimal | None, *, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.{digits}f}%"


def _num(value: Decimal | None, *, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def _ratio(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


def render_account_pdf(
    *,
    email: str,
    books: list[dict[str, Any]],
) -> bytes:
    """Build a multi-portfolio summary PDF.

    Each book dict may include:
    - name, description, is_paper
    - positions: PositionsResponse | None
    - analytics: AnalyticsOut | None
    - goals: list[GoalOut]
    - analytics_note: str | None
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title="Portfolytix portfolio report",
        author="Portfolytix",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=4,
        textColor=colors.HexColor("#1a2332"),
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#5b6573"),
        spaceAfter=14,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=13,
        spaceBefore=12,
        spaceAfter=6,
        textColor=colors.HexColor("#1a2332"),
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#2c3340"),
    )
    muted_style = ParagraphStyle(
        "Muted",
        parent=body_style,
        textColor=colors.HexColor("#5b6573"),
        spaceAfter=8,
    )

    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    story: list[Any] = [
        Paragraph("Portfolytix portfolio report", title_style),
        Paragraph(
            f"Account: {email}<br/>Generated: {generated}",
            subtitle_style,
        ),
        Paragraph(
            "Summary of holdings, performance, and goals. "
            "Figures can be delayed. Not investment advice.",
            muted_style,
        ),
    ]

    if not books:
        story.append(Paragraph("No portfolios on this account.", body_style))
    else:
        for book in books:
            story.extend(
                _portfolio_section(
                    book,
                    section_style,
                    body_style,
                    muted_style,
                )
            )

    doc.build(story)
    return buffer.getvalue()


def _portfolio_section(
    book: dict[str, Any],
    section_style: ParagraphStyle,
    body_style: ParagraphStyle,
    muted_style: ParagraphStyle,
) -> list[Any]:
    name = str(book.get("name") or "Portfolio")
    paper = " (practice)" if book.get("is_paper") else ""
    description = (book.get("description") or "").strip()
    positions: PositionsResponse | None = book.get("positions")
    analytics: AnalyticsOut | None = book.get("analytics")
    goals: list[GoalOut] = list(book.get("goals") or [])
    analytics_note: str | None = book.get("analytics_note")

    parts: list[Any] = [
        Paragraph(f"{name}{paper}", section_style),
    ]
    if description:
        parts.append(Paragraph(description, muted_style))

    if positions is None:
        parts.append(Paragraph("Positions unavailable.", muted_style))
        return parts

    summary_rows = [
        ["Market value", _money(positions.market_value)],
        ["Cost basis", _money(positions.cost_basis)],
        ["Unrealized P/L", _money(positions.unrealized_pl)],
        ["Day P/L", _money(positions.day_pl)],
        ["Cash", _money(positions.cash)],
        ["Realized P/L", _money(positions.realized_pl)],
    ]
    parts.append(_kv_table(summary_rows))
    parts.append(Spacer(1, 8))

    if analytics is not None:
        parts.append(Paragraph("<b>Performance</b>", body_style))
        perf_rows = [
            ["Total return", _pct(analytics.total_return)],
            ["Annualized return", _pct(analytics.annualized_return)],
            ["Volatility (ann.)", _pct(analytics.volatility)],
            ["Sharpe ratio", _ratio(analytics.sharpe_ratio)],
            ["Max drawdown", _pct(analytics.max_drawdown)],
        ]
        if analytics.benchmark_ticker:
            perf_rows.append(
                [
                    f"Benchmark ({analytics.benchmark_ticker})",
                    _pct(analytics.benchmark_return),
                ]
            )
            perf_rows.append(["Beta", _ratio(analytics.benchmark_beta)])
        parts.append(_kv_table(perf_rows))
        parts.append(Spacer(1, 8))
    elif analytics_note:
        parts.append(Paragraph(f"Performance: {analytics_note}", muted_style))

    if positions.positions:
        parts.append(Paragraph("<b>Holdings</b>", body_style))
        header = ["Ticker", "Qty", "Avg cost", "Price", "Value", "Weight", "P/L"]
        rows: list[list[str]] = [header]
        ordered = sorted(
            positions.positions,
            key=lambda row: row.market_value or Decimal("0"),
            reverse=True,
        )
        for row in ordered:
            rows.append(
                [
                    row.ticker,
                    _num(row.quantity, digits=0),
                    _money(row.average_cost or row.avg_cost),
                    _money(row.current_price or row.price),
                    _money(row.market_value),
                    _pct(row.weight),
                    _money(row.unrealized_pl),
                ]
            )
        parts.append(_data_table(rows, col_widths=[55, 45, 70, 65, 75, 55, 70]))
        parts.append(Spacer(1, 8))
    else:
        parts.append(Paragraph("No open holdings.", muted_style))

    if positions.sector_allocation:
        parts.append(Paragraph("<b>Sector allocation</b>", body_style))
        sector_rows = [["Sector", "Value", "Weight"]]
        for bucket in positions.sector_allocation[:12]:
            sector_rows.append(
                [bucket.label, _money(bucket.market_value), _pct(bucket.weight)]
            )
        parts.append(_data_table(sector_rows, col_widths=[220, 90, 70]))
        parts.append(Spacer(1, 8))

    if goals:
        parts.append(Paragraph("<b>Goals</b>", body_style))
        goal_rows = [["Goal", "Target", "Date", "Progress"]]
        for goal in goals:
            goal_rows.append(
                [
                    goal.name,
                    _money(goal.target_amount),
                    goal.target_date.isoformat(),
                    _pct(goal.progress),
                ]
            )
        parts.append(_data_table(goal_rows, col_widths=[180, 90, 80, 70]))
        parts.append(Spacer(1, 8))

    return parts


def _kv_table(rows: list[list[str]]) -> Table:
    table = Table(rows, colWidths=[160, 120])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#5b6573")),
                ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#1a2332")),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _data_table(rows: list[list[str]], col_widths: list[float]) -> Table:
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f6")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1a2332")),
                ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#2c3340")),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("ALIGN", (0, 0), (0, -1), "LEFT"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d5dce3")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table
