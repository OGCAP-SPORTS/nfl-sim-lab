"""Build transparent OGCAP team scoring baselines from completed NFL games.
Source: nflverse/nfldata games.csv. No invented stats; no pregame leakage.
This is a scoring baseline, NOT an EPA model or validated betting projection.
"""
import io, urllib.request
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

SOURCE = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
NAMES = {
"ARI":"Arizona Cardinals","ATL":"Atlanta Falcons","BAL":"Baltimore Ravens",
"BUF":"Buffalo Bills","CAR":"Carolina Panthers","CHI":"Chicago Bears",
"CIN":"Cincinnati Bengals","CLE":"Cleveland Browns","DAL":"Dallas Cowboys",
"DEN":"Denver Broncos","DET":"Detroit Lions","GB":"Green Bay Packers",
"HOU":"Houston Texans","IND":"Indianapolis Colts","JAX":"Jacksonville Jaguars",
"KC":"Kansas City Chiefs","LA":"Los Angeles Rams","LAC":"Los Angeles Chargers",
"LV":"Las Vegas Raiders","MIA":"Miami Dolphins","MIN":"Minnesota Vikings",
"NE":"New England Patriots","NO":"New Orleans Saints","NYG":"New York Giants",
"NYJ":"New York Jets","PHI":"Philadelphia Eagles","PIT":"Pittsburgh Steelers",
"SEA":"Seattle Seahawks","SF":"San Francisco 49ers","TB":"Tampa Bay Buccaneers",
"TEN":"Tennessee Titans","WAS":"Washington Commanders"}
ALIASES={"OAK":"LV","SD":"LAC","STL":"LA","JAC":"JAX","WSH":"WAS"}
def build(df, now=None):
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None: now=now.tz_localize("UTC")
    required={"season","gameday","home_team","away_team","home_score","away_score"}
    missing=required-set(df.columns)
    if missing: raise ValueError(f"Missing source columns: {sorted(missing)}")
    df=df.copy()
    df["season"]=pd.to_numeric(df["season"],errors="coerce")
    df["gameday"]=pd.to_datetime(df["gameday"],errors="coerce",utc=True)
    for c in ("home_score","away_score"): df[c]=pd.to_numeric(df[c],errors="coerce")
    for c in ("home_team","away_team"): df[c]=df[c].replace(ALIASES)
    # Date-only gameday is used; exclude current UTC date to avoid including in-progress games.
    cutoff=now.normalize()
    df=df[(df.season.isin([2025,2026]))&(df.gameday<cutoff)&
          df.home_score.notna()&df.away_score.notna()]
    if "game_type" in df.columns: df=df[df.game_type.eq("REG")]
    rows=[]
    for _,g in df.iterrows():
        rows.append((g.home_team,int(g.season),float(g.home_score),float(g.away_score)))
        rows.append((g.away_team,int(g.season),float(g.away_score),float(g.home_score)))
    game_rows=pd.DataFrame(rows,columns=["team","season","pf","pa"])
    output=[]
    for abbr,name in NAMES.items():
        t=game_rows[game_rows.team.eq(abbr)]
        y25=t[t.season.eq(2025)]
        y26=t[t.season.eq(2026)]
        if y25.empty and y26.empty: raise ValueError(f"No completed games for {abbr}")
        # 2025 is prior; 2026 gets progressively more weight as completed games accumulate.
        weight26=min(0.8,len(y26)/(len(y26)+8)) if len(y26) else 0
        if y25.empty: weight26=1
        if y26.empty: weight26=0
        def blended(col):
            v25=y25[col].mean() if len(y25) else 0
            v26=y26[col].mean() if len(y26) else 0
            return round((1-weight26)*v25+weight26*v26,3)
        output.append(dict(team=name,off_ppg=blended("pf"),def_ppg=blended("pa"),
            games_2025=len(y25),games_2026=len(y26),weight_2026=round(weight26,3),
            data_through_utc=str((cutoff-pd.Timedelta(days=1)).date())))
    out=pd.DataFrame(output)
    if len(out)!=32 or out[["off_ppg","def_ppg"]].isna().any().any():
        raise ValueError("Ratings validation failed")
    return out

def main():
    req=urllib.request.Request(SOURCE,headers={"User-Agent":"OGCAP-NFL-Sim-Lab/1.0"})
    with urllib.request.urlopen(req,timeout=45) as response:
        raw=response.read()
    df=pd.read_csv(io.BytesIO(raw),low_memory=False)
    ratings=build(df)
    out=Path("team_ratings.csv")
    # The V2 dashboard expects exactly these first three headers.
    ratings[["team","off_ppg","def_ppg"]].to_csv(out,index=False)
    ratings.to_csv("team_ratings_audit.csv",index=False)
    print("Built 32 team scoring baselines from completed games.")
    print(ratings[["games_2025","games_2026"]].sum().to_string())

if __name__=="__main__": main()
