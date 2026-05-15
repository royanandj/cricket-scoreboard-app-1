from pathlib import Path
import sqlite3
from datetime import date
import pandas as pd
import streamlit as st

DB = Path("cricket_app.db")

st.set_page_config(page_title="CricStyle Scorer", page_icon="🏏", layout="wide")
st.markdown("""
<style>
.block-container{padding:0.75rem 0.75rem 2rem;max-width:1120px}
.stButton>button{width:100%;height:3.15rem;border-radius:14px;font-weight:800;font-size:1rem}
.stDownloadButton>button{width:100%;border-radius:12px}
div[data-testid="stMetric"]{background:#f5f7fb;border-radius:16px;padding:12px;border:1px solid #e5e7eb}
input,select,textarea{font-size:16px!important}
.scorebox{background:#0f172a;color:white;border-radius:22px;padding:16px;margin:8px 0}
.scorebig{font-size:2.2rem;font-weight:900;line-height:1.1}.small{opacity:.85;font-size:.95rem}
.card{background:#ffffff;border:1px solid #e5e7eb;border-radius:18px;padding:14px;margin:8px 0}
@media(max-width:768px){.block-container{padding-left:.55rem;padding-right:.55rem}div[data-testid="column"]{width:100%!important;flex:unset}.scorebig{font-size:1.8rem}.stDataFrame{font-size:12px}}
</style>
""", unsafe_allow_html=True)

# ---------- DB ----------
def con():
    c = sqlite3.connect(DB, check_same_thread=False)
    c.execute("PRAGMA foreign_keys=ON")
    return c
conn = con()
conn.executescript("""
CREATE TABLE IF NOT EXISTS tournaments(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,overs REAL NOT NULL DEFAULT 5,points_win INTEGER DEFAULT 2,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS teams(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,captain TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS players(id INTEGER PRIMARY KEY AUTOINCREMENT,team_id INTEGER NOT NULL,name TEXT NOT NULL,role TEXT DEFAULT '',UNIQUE(team_id,name),FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS matches(id INTEGER PRIMARY KEY AUTOINCREMENT,tournament_id INTEGER,match_date TEXT,venue TEXT DEFAULT '',team_a INTEGER NOT NULL,team_b INTEGER NOT NULL,overs REAL NOT NULL,toss_winner INTEGER,elected TEXT DEFAULT '',status TEXT DEFAULT 'Setup',innings_no INTEGER DEFAULT 1,winner_id INTEGER,result_text TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(tournament_id) REFERENCES tournaments(id),FOREIGN KEY(team_a) REFERENCES teams(id),FOREIGN KEY(team_b) REFERENCES teams(id));
CREATE TABLE IF NOT EXISTS innings(id INTEGER PRIMARY KEY AUTOINCREMENT,match_id INTEGER NOT NULL,innings_no INTEGER NOT NULL,batting_team INTEGER NOT NULL,bowling_team INTEGER NOT NULL,target INTEGER DEFAULT 0,is_complete INTEGER DEFAULT 0,FOREIGN KEY(match_id) REFERENCES matches(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS balls(id INTEGER PRIMARY KEY AUTOINCREMENT,innings_id INTEGER NOT NULL,ball_no INTEGER NOT NULL,runs_bat INTEGER DEFAULT 0,extras INTEGER DEFAULT 0,extra_type TEXT DEFAULT '',is_legal INTEGER DEFAULT 1,is_wicket INTEGER DEFAULT 0,wicket_type TEXT DEFAULT '',batter TEXT DEFAULT '',bowler TEXT DEFAULT '',note TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(innings_id) REFERENCES innings(id) ON DELETE CASCADE);
""")
conn.commit()

def q(sql, params=()): return pd.read_sql_query(sql, conn, params=params)
def ex(sql, params=()):
    cur=conn.execute(sql, params); conn.commit(); return cur.lastrowid

def overs_to_balls(v):
    whole=int(float(v)); b=int(round((float(v)-whole)*10))
    if b<0 or b>5: raise ValueError("Use cricket overs format: 4.5 means 4 overs and 5 balls.")
    return whole*6+b

def balls_to_overs(b): return f"{b//6}.{b%6}"
def team_name(tid):
    r=q("select name from teams where id=?",(tid,)); return "" if r.empty else r.iloc[0,0]
def opts(table):
    df=q(f"select id,name from {table} order by name"); return {r['name']:int(r['id']) for _,r in df.iterrows()}

def innings_stats(inn_id):
    b=q("select * from balls where innings_id=? order by ball_no,id",(inn_id,))
    runs=int((b.runs_bat+b.extras).sum()) if not b.empty else 0
    wk=int(b.is_wicket.sum()) if not b.empty else 0
    legal=int(b.is_legal.sum()) if not b.empty else 0
    return runs,wk,legal,b

def current_match():
    df=q("select * from matches where status in ('Live','Setup') order by id desc limit 1")
    return None if df.empty else df.iloc[0].to_dict()

def ensure_innings(mid):
    m=q("select * from matches where id=?",(mid,)).iloc[0]
    inn=q("select * from innings where match_id=? order by innings_no",(mid,))
    if inn.empty:
        bat=m.team_a if m.elected!='Bowl' else m.team_b if m.toss_winner==m.team_a else m.team_a
        # simpler: team_a bats first by default unless toss winner chose bowl
        if m.toss_winner==m.team_a and m.elected=='Bowl': bat=m.team_b
        if m.toss_winner==m.team_b and m.elected=='Bowl': bat=m.team_a
        bowl=m.team_b if bat==m.team_a else m.team_a
        ex("insert into innings(match_id,innings_no,batting_team,bowling_team) values(?,?,?,?)",(mid,1,bat,bowl))
    ex("update matches set status='Live' where id=?",(mid,))

def active_innings(mid):
    ensure_innings(mid)
    inn=q("select * from innings where match_id=? and is_complete=0 order by innings_no limit 1",(mid,))
    if inn.empty: return None
    return inn.iloc[0].to_dict()

def complete_innings(mid, inn):
    runs,wk,legal,_=innings_stats(inn['id'])
    ex("update innings set is_complete=1 where id=?",(inn['id'],))
    if int(inn['innings_no'])==1:
        m=q("select * from matches where id=?",(mid,)).iloc[0]
        ex("insert into innings(match_id,innings_no,batting_team,bowling_team,target) values(?,?,?,?,?)",(mid,2,inn['bowling_team'],inn['batting_team'],runs+1))
        ex("update matches set innings_no=2 where id=?",(mid,))
    else:
        finish_match(mid)

def finish_match(mid):
    inn=q("select * from innings where match_id=? order by innings_no",(mid,))
    if len(inn)<2: return
    r1=innings_stats(int(inn.iloc[0].id))[0]; r2=innings_stats(int(inn.iloc[1].id))[0]
    t1=int(inn.iloc[0].batting_team); t2=int(inn.iloc[1].batting_team)
    if r1>r2: win=t1; txt=f"{team_name(t1)} won by {r1-r2} runs"
    elif r2>r1:
        wk=innings_stats(int(inn.iloc[1].id))[1]; win=t2; txt=f"{team_name(t2)} won by {10-wk} wickets"
    else: win=None; txt="Match tied"
    ex("update matches set status='Completed',winner_id=?,result_text=? where id=?",(win,txt,mid))

# ---------- Sidebar setup ----------
st.sidebar.title("🏏 CricStyle")
page=st.sidebar.radio("Menu",["Live Scoring","New Match","Teams & Players","Points Table","Scorecards","Backup"])

# ---------- Teams ----------
if page=="Teams & Players":
    st.title("Teams & Players")
    with st.expander("Add teams", expanded=True):
        names=st.text_area("Team names, one per line", placeholder="Warriors\nTitans\nStrikers")
        cap=st.text_input("Captain optional")
        if st.button("Save teams"):
            for n in [x.strip() for x in names.splitlines() if x.strip()]: ex("insert or ignore into teams(name,captain) values(?,?)",(n,cap))
            st.success("Teams saved"); st.rerun()
    teams=opts('teams')
    if teams:
        team=st.selectbox("Add players to",list(teams.keys()))
        players=st.text_area("Player names, one per line")
        if st.button("Save players"):
            for p in [x.strip() for x in players.splitlines() if x.strip()]: ex("insert or ignore into players(team_id,name) values(?,?)",(teams[team],p))
            st.success("Players saved")
    st.dataframe(q("select t.name Team, t.captain Captain, coalesce(group_concat(p.name, ', '),'') Players from teams t left join players p on p.team_id=t.id group by t.id order by t.name"), use_container_width=True, hide_index=True)

# ---------- New Match ----------
elif page=="New Match":
    st.title("Create Match")
    tmap=opts('teams')
    if len(tmap)<2: st.warning("Add at least two teams first."); st.stop()
    with st.form("newmatch"):
        comp=st.text_input("Tournament name", value="Office Cricket Tournament")
        overs=st.number_input("Overs",1.0,50.0,5.0,1.0)
        venue=st.text_input("Venue")
        c1,c2=st.columns(2)
        a=c1.selectbox("Team A",list(tmap.keys()))
        b=c2.selectbox("Team B",[x for x in tmap if x!=a])
        toss=st.selectbox("Toss winner",[a,b])
        elected=st.selectbox("Elected to",["Bat","Bowl"])
        submitted=st.form_submit_button("Start match")
    if submitted:
        tid=ex("insert or ignore into tournaments(name,overs) values(?,?)",(comp,overs))
        tid=q("select id from tournaments where name=?",(comp,)).iloc[0,0]
        mid=ex("insert into matches(tournament_id,match_date,venue,team_a,team_b,overs,toss_winner,elected,status) values(?,?,?,?,?,?,?,?,?)",(tid,str(date.today()),venue,tmap[a],tmap[b],overs,tmap[toss],elected,'Setup'))
        ensure_innings(mid); st.success("Match started. Go to Live Scoring.")

# ---------- Live ----------
elif page=="Live Scoring":
    st.title("Live Scoring")
    m=current_match()
    if not m: st.info("No live match. Create one from New Match."); st.stop()
    inn=active_innings(m['id'])
    if not inn: st.success("Match completed."); st.write(q("select result_text from matches where id=?",(m['id'],)).iloc[0,0]); st.stop()
    max_balls=overs_to_balls(m['overs'])
    runs,wk,legal,balls=innings_stats(inn['id'])
    target=int(inn.get('target') or 0)
    rr = runs/(legal/6) if legal else 0
    need = max(target-runs,0) if target else None
    st.markdown(f"""<div class='scorebox'><div class='small'>{team_name(inn['batting_team'])} batting vs {team_name(inn['bowling_team'])}</div><div class='scorebig'>{runs}/{wk} <span style='font-size:1.1rem'>({balls_to_overs(legal)} ov)</span></div><div class='small'>Run rate: {rr:.2f} {('| Target: '+str(target)+' | Need: '+str(need)) if target else ''}</div></div>""", unsafe_allow_html=True)
    if target and runs>=target: complete_innings(m['id'],inn); st.rerun()
    if legal>=max_balls or wk>=10: complete_innings(m['id'],inn); st.rerun()

    st.subheader("Tap one ball")
    batter=st.text_input("Batter optional", key="bat")
    bowler=st.text_input("Bowler optional", key="bowl")
    def add_ball(rb=0,exr=0,etype='',legal_ball=True,wicket=False,wtype=''):
        n=int(q("select coalesce(max(ball_no),0)+1 from balls where innings_id=?",(inn['id'],)).iloc[0,0])
        ex("insert into balls(innings_id,ball_no,runs_bat,extras,extra_type,is_legal,is_wicket,wicket_type,batter,bowler) values(?,?,?,?,?,?,?,?,?,?)",(inn['id'],n,rb,exr,etype,1 if legal_ball else 0,1 if wicket else 0,wtype,batter,bowler))
    c=st.columns(4)
    for i,r in enumerate([0,1,2,3]):
        if c[i].button(str(r)): add_ball(rb=r); st.rerun()
    c=st.columns(4)
    if c[0].button("4"): add_ball(rb=4); st.rerun()
    if c[1].button("6"): add_ball(rb=6); st.rerun()
    if c[2].button("Wicket"): add_ball(rb=0,wicket=True,wtype='Out'); st.rerun()
    if c[3].button("Undo last"):
        last=q("select id from balls where innings_id=? order by id desc limit 1",(inn['id'],))
        if not last.empty: ex("delete from balls where id=?",(int(last.iloc[0,0]),)); st.rerun()
    st.markdown("### Extras")
    c=st.columns(4)
    if c[0].button("Wide +1"): add_ball(exr=1,etype='Wd',legal_ball=False); st.rerun()
    if c[1].button("No ball +1"): add_ball(exr=1,etype='NB',legal_ball=False); st.rerun()
    if c[2].button("Bye +1"): add_ball(exr=1,etype='B'); st.rerun()
    if c[3].button("Leg bye +1"): add_ball(exr=1,etype='LB'); st.rerun()
    if st.button("End innings now"):
        complete_innings(m['id'],inn); st.rerun()
    st.markdown("### Ball log")
    if not balls.empty:
        log=balls[['ball_no','runs_bat','extras','extra_type','is_wicket','batter','bowler']].copy()
        log['Ball']=range(1,len(log)+1)
        log['Score']=log['runs_bat']+log['extras']
        st.dataframe(log[['Ball','Score','extra_type','is_wicket','batter','bowler']].tail(24), use_container_width=True, hide_index=True)

# ---------- Points ----------
elif page=="Points Table":
    st.title("Points Table")
    teams=q("select * from teams order by name"); matches=q("select * from matches where status='Completed'"); inns=q("select * from innings")
    rows=[]
    for _,t in teams.iterrows():
        tid=int(t.id); ms=matches[(matches.team_a==tid)|(matches.team_b==tid)]
        p=len(ms); w=len(ms[ms.winner_id==tid]); tie=len(ms[ms.winner_id.isna()]); l=p-w-tie
        rf=ra=bf=ba=0
        for _,inn in inns.iterrows():
            if int(inn.batting_team)==tid or int(inn.bowling_team)==tid:
                r,wk,legal,_=innings_stats(int(inn.id)); mrow=matches[matches.id==inn.match_id]
                if mrow.empty: continue
                mb=overs_to_balls(float(mrow.iloc[0].overs))
                use_balls=mb if wk>=10 else legal
                if int(inn.batting_team)==tid: rf+=r; bf+=use_balls
                if int(inn.bowling_team)==tid: ra+=r; ba+=use_balls
        nrr=(rf/(bf/6) if bf else 0)-(ra/(ba/6) if ba else 0)
        rows.append({'Team':t['name'],'P':p,'W':w,'L':l,'T/NR':tie,'Pts':w*2+tie,'NRR':round(nrr,3),'Runs For':rf,'Runs Against':ra})
    df=pd.DataFrame(rows).sort_values(['Pts','NRR','W'],ascending=[False,False,False]) if rows else pd.DataFrame()
    st.dataframe(df,use_container_width=True,hide_index=True)
    if not df.empty: st.download_button("Download CSV", df.to_csv(index=False), "points_table.csv")

# ---------- Scorecards ----------
elif page=="Scorecards":
    st.title("Scorecards")
    ms=q("select m.id,m.match_date,t1.name Team_A,t2.name Team_B,m.status,m.result_text from matches m join teams t1 on t1.id=m.team_a join teams t2 on t2.id=m.team_b order by m.id desc")
    if ms.empty: st.info("No matches yet."); st.stop()
    st.dataframe(ms.drop(columns=['id']),use_container_width=True,hide_index=True)
    mid=st.selectbox("Open match",ms.id.tolist(),format_func=lambda x: f"#{x} {ms[ms.id==x].iloc[0].Team_A} vs {ms[ms.id==x].iloc[0].Team_B}")
    for _,inn in q("select * from innings where match_id=? order by innings_no",(mid,)).iterrows():
        r,w,l,b=innings_stats(int(inn.id))
        st.markdown(f"<div class='card'><b>{team_name(inn.batting_team)}</b> {r}/{w} ({balls_to_overs(l)} ov)</div>",unsafe_allow_html=True)
        if not b.empty: st.dataframe(b[['ball_no','runs_bat','extras','extra_type','is_wicket','batter','bowler']],use_container_width=True,hide_index=True)
    if st.button("Delete this match"):
        ex("delete from matches where id=?",(mid,)); st.success("Deleted"); st.rerun()

# ---------- Backup ----------
else:
    st.title("Backup / Restore")
    if DB.exists(): st.download_button("Download database backup", DB.read_bytes(), "cricket_app_backup.db")
    up=st.file_uploader("Restore backup", type=['db','sqlite','sqlite3'])
    if up and st.button("Restore now"):
        conn.close(); DB.write_bytes(up.getvalue()); st.success("Restored. Refresh the app.")
