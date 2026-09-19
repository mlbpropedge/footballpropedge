import pandas as pd
from src.features import make_training_frame, feature_columns

def test_feature_builder_has_no_current_game_leakage():
    rows=[]
    for week,yards in enumerate([10,20,30,40],start=1):
        rows.append({"player_id":"p1","player_display_name":"Player One","position":"RB","recent_team":"AAA","season":2025,"week":week,"carries":10,"rushing_yards":yards,"rushing_tds":0,"targets":2,"receptions":1,"receiving_yards":5,"receiving_tds":0})
    out=make_training_frame(pd.DataFrame(rows))
    week3=out[out.week==3].iloc[0]
    assert week3["rushing_yards_avg_3"]==15
    assert set(feature_columns()).issubset(out.columns)
