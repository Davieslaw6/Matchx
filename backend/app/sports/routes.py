"""Owner-authenticated fixture explorer API."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.auth import require_owner
from app.db import get_db
from app.models import Competition, Fixture, Prediction, Team, Session

router = APIRouter(prefix="/api/v1/fixtures", tags=["fixtures"])

class FixtureItem(BaseModel):
    id: str
    competition: str
    home_team: str
    away_team: str
    match_date: date | None
    kickoff_at: str | None
    status: str
    prediction_available: bool

class FixturePage(BaseModel):
    items: list[FixtureItem]
    page: int
    page_size: int
    total: int

@router.get("", response_model=FixturePage)
async def list_fixtures(
    start_date: date | None = None,
    end_date: date | None = None,
    competition_id: str | None = None,
    status: Literal["scheduled", "live", "finished", "postponed", "abandoned", "cancelled"] | None = None,
    team: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=25, ge=1, le=100),
    _: Session = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    if start_date and end_date and end_date < start_date:
        raise HTTPException(status_code=422, detail={"code":"invalid_date_range","message":"end_date must not precede start_date."})
    home = aliased(Team)
    away = aliased(Team)
    base = select(Fixture.id, Competition.name.label("competition"), home.name.label("home"),
                  away.name.label("away"), Fixture.match_date, Fixture.kickoff_at,
                  Fixture.status).join(Competition, Fixture.competition_id == Competition.id) \
                  .join(home, Fixture.home_team_id == home.id) \
                  .join(away, Fixture.away_team_id == away.id)
    count_query = select(func.count(Fixture.id))
    predicates = []
    if start_date:
        predicates.append(Fixture.match_date >= start_date)
    if end_date:
        predicates.append(Fixture.match_date <= end_date)
    if competition_id:
        predicates.append(Fixture.competition_id == competition_id)
    if status:
        predicates.append(Fixture.status == status)
    if team:
        pattern = f"%{team.strip()}%"
        predicates.append(or_(home.name.ilike(pattern), away.name.ilike(pattern)))
    for predicate in predicates:
        base = base.where(predicate)
        count_query = count_query.join(Competition, Fixture.competition_id == Competition.id) if False else count_query
    # Count filtering uses EXISTS for team matching, avoiding duplicate rows from joins.
    count_query = select(func.count(Fixture.id)).select_from(Fixture)
    if start_date:
        count_query = count_query.where(Fixture.match_date >= start_date)
    if end_date:
        count_query = count_query.where(Fixture.match_date <= end_date)
    if competition_id:
        count_query = count_query.where(Fixture.competition_id == competition_id)
    if status:
        count_query = count_query.where(Fixture.status == status)
    if team:
        pattern = f"%{team.strip()}%"
        count_query = count_query.where(
            or_(Fixture.home_team_id.in_(select(Team.id).where(Team.name.ilike(pattern))),
                Fixture.away_team_id.in_(select(Team.id).where(Team.name.ilike(pattern))))
        )
    total = int(await db.scalar(count_query) or 0)
    prediction_exists = select(Prediction.id).where(Prediction.fixture_id == Fixture.id).exists()
    rows = (await db.execute(base.add_columns(prediction_exists.label("prediction_available"))
        .order_by(Fixture.kickoff_at.asc().nulls_last(), Fixture.match_date.asc().nulls_last())
        .offset((page - 1) * page_size).limit(page_size))).all()
    items = [FixtureItem(id=row.id, competition=row.competition, home_team=row.home,
             away_team=row.away, match_date=row.match_date,
             kickoff_at=row.kickoff_at.isoformat() if row.kickoff_at else None,
             status=row.status, prediction_available=bool(row.prediction_available)) for row in rows]
    return FixturePage(items=items, page=page, page_size=page_size, total=total)
