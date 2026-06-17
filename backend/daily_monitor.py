import os
import json
import sys
from datetime import datetime

# Reconfigure stdout/stderr for Windows UTF-8 terminal
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backend", "data")

def main():
    # Define active simulated tracks reflecting the SOP stage timeline
    active_tracks = [
        {
            "stock_code": "8155",
            "company_name": "博智",
            "bond_name": "博智二",
            "expected_listing_date": "2026-07-06",
            "current_stage_index": 4, # At Holding stage
            "status_text": "符合條件：籌碼判定通過，買入持股中",
            "status_type": "success",
            "strategy_info": {
                "name": "策略 1: 外資定價前卡位",
                "win_rate": 100.0,
                "avg_return": 45.0
            },
            "stations": [
                {
                    "name": "競拍公告發布",
                    "date": "2026-06-10",
                    "status": "completed",
                    "description": "公會公告博智二發行時程，定價掛牌日為 2026-07-06。"
                },
                {
                    "name": "T-15 籌碼審查",
                    "date": "2026-06-15",
                    "status": "completed",
                    "description": "累積外資買超 2,450 張，大於 2,000 張門檻，符合進場條件！"
                },
                {
                    "name": "T-14 策略買進",
                    "date": "2026-06-16",
                    "status": "completed",
                    "description": "開盤以 $142.5 元買進普通股現貨。"
                },
                {
                    "name": "T日 掛牌上市",
                    "date": "2026-07-06",
                    "status": "active",
                    "description": "即將正式掛牌發行，預期現貨有拉抬動能。"
                },
                {
                    "name": "T+1~18 拆解拉抬",
                    "date": "2026-07-07",
                    "status": "upcoming",
                    "description": "持有至選擇權拆解日，鎖定槓桿買盤行情。"
                },
                {
                    "name": "T+19 結算出場",
                    "date": "2026-08-03",
                    "status": "upcoming",
                    "description": "預定收盤無條件賣出結算。"
                }
            ],
            "performance": {
                "buy_price": 142.5,
                "current_price": 150.0,
                "return_pct": 5.26
            }
        },
        {
            "stock_code": "6187",
            "company_name": "萬潤",
            "bond_name": "萬潤六",
            "expected_listing_date": "2026-07-02",
            "current_stage_index": 0, # Bidding / upcoming check
            "status_text": "正在競拍中，開標日 06/23，靜待掛牌公告與複審",
            "status_type": "pending",
            "strategy_info": {
                "name": "策略 4: 投信卡位 + 股本佔比型",
                "win_rate": 100.0,
                "avg_return": 43.6
            },
            "stations": [
                {
                    "name": "競拍公告與投標",
                    "date": "2026-06-16",
                    "status": "active",
                    "description": "公會公告萬潤六發行時程，競拍投標期間為 2026-06-16 至 2026-06-18。"
                },
                {
                    "name": "競拍開標與結果",
                    "date": "2026-06-23",
                    "status": "upcoming",
                    "description": "訂於 06/23 進行公開競價拍賣開標並公告結果。"
                },
                {
                    "name": "T-15 籌碼複審",
                    "date": "2026-06-11",
                    "status": "completed",
                    "description": "掛牌日回推 15 日為 06/11。因尚在競拍程序中，將於 06/23 開標後重新複審投信籌碼是否符合大於 2,000 張且佔比大於 0.5%。"
                },
                {
                    "name": "T-14 策略買進",
                    "date": "2026-06-12",
                    "status": "upcoming",
                    "description": "若判定符合條件，開盤買進現貨股票。"
                },
                {
                    "name": "T日 掛牌上市",
                    "date": "2026-07-02",
                    "status": "upcoming",
                    "description": "萬潤六預計正式掛牌上市交易。"
                },
                {
                    "name": "T+19 結算出場",
                    "date": "2026-07-29",
                    "status": "upcoming",
                    "description": "預定收盤無條件賣出結算。"
                }
            ],
            "performance": None
        },
        {
            "stock_code": "3260",
            "company_name": "威剛",
            "bond_name": "威剛八",
            "expected_listing_date": "2026-07-13",
            "current_stage_index": 1, # Awaiting T-15 Check
            "status_text": "已發布競拍公告，靜待 T-15 籌碼判定點",
            "status_type": "pending",
            "strategy_info": {
                "name": "策略 2: 投信定價前卡位",
                "win_rate": 100.0,
                "avg_return": 42.9
            },
            "stations": [
                {
                    "name": "競拍公告發布",
                    "date": "2026-06-16",
                    "status": "completed",
                    "description": "公會已公告威剛八競拍辦法，預計 2026-07-13 掛牌。"
                },
                {
                    "name": "T-15 籌碼審查",
                    "date": "2026-06-22",
                    "status": "active",
                    "description": "預定 6/22 收盤判定外資/投信累積張數。"
                },
                {
                    "name": "T-14 策略買進",
                    "date": "2026-06-23",
                    "status": "upcoming",
                    "description": "若審查通過，將於開盤進行買入。"
                },
                {
                    "name": "T日 掛牌上市",
                    "date": "2026-07-13",
                    "status": "upcoming",
                    "description": "預定掛牌日。"
                },
                {
                    "name": "T+1~18 拆解拉抬",
                    "date": "2026-07-14",
                    "status": "upcoming",
                    "description": "待執行持股波段。"
                },
                {
                    "name": "T+19 結算出場",
                    "date": "2026-08-10",
                    "status": "upcoming",
                    "description": "預定出場日。"
                }
            ],
            "performance": None
        },
        {
            "stock_code": "6584",
            "company_name": "南俊國際",
            "bond_name": "南俊國際一",
            "expected_listing_date": "2026-07-10",
            "current_stage_index": 1, # Awaiting T-15 Check
            "status_text": "已發布競拍公告，靜待 T-15 籌碼判定點",
            "status_type": "pending",
            "strategy_info": {
                "name": "策略 4: 投信卡位 + 股本佔比型",
                "win_rate": 100.0,
                "avg_return": 43.6
            },
            "stations": [
                {
                    "name": "競拍公告發布",
                    "date": "2026-06-16",
                    "status": "completed",
                    "description": "公會已公告南俊國際一競拍時程，預計 2026-07-10 掛牌。"
                },
                {
                    "name": "T-15 籌碼審查",
                    "date": "2026-06-19",
                    "status": "active",
                    "description": "預定 06/19 收盤判定投信累積買超張數與公司股本佔比是否符合條件。"
                },
                {
                    "name": "T-14 策略買進",
                    "date": "2026-06-22",
                    "status": "upcoming",
                    "description": "若審查通過，將於開盤進行買入。"
                },
                {
                    "name": "T日 掛牌上市",
                    "date": "2026-07-10",
                    "status": "upcoming",
                    "description": "南俊國際一預定掛牌日。"
                },
                {
                    "name": "T+1~18 拆解拉抬",
                    "date": "2026-07-13",
                    "status": "upcoming",
                    "description": "待執行持股波段。"
                },
                {
                    "name": "T+19 結算出場",
                    "date": "2026-08-06",
                    "status": "upcoming",
                    "description": "預定結算出場日。"
                }
            ],
            "performance": None
        },
        {
            "stock_code": "3702",
            "company_name": "大聯大",
            "bond_name": "大聯大二",
            "expected_listing_date": "2026-07-03",
            "current_stage_index": 2, # Failed check
            "status_text": "不符合條件：T-15 籌碼審查不符，已放棄交易",
            "status_type": "failed",
            "strategy_info": {
                "name": "策略 2: 投信定價前卡位",
                "win_rate": 100.0,
                "avg_return": 42.9
            },
            "stations": [
                {
                    "name": "競拍公告發布",
                    "date": "2026-06-12",
                    "status": "completed",
                    "description": "大聯大二競拍時程公告，預計 2026-07-03 掛牌。"
                },
                {
                    "name": "T-15 籌碼審查",
                    "date": "2026-06-15",
                    "status": "failed",
                    "description": "❌ 籌碼不符：投信累積買超僅 250 張，未達 2,000 張門檻且佔股本 0.015% 未達 0.5%。"
                },
                {
                    "name": "T-14 策略買進",
                    "date": "2026-06-16",
                    "status": "upcoming",
                    "description": "已放棄買進。"
                },
                {
                    "name": "T日 掛牌上市",
                    "date": "2026-07-03",
                    "status": "upcoming",
                    "description": "無持股掛牌。"
                },
                {
                    "name": "T+1~18 拆解拉抬",
                    "date": "2026-07-06",
                    "status": "upcoming",
                    "description": "無動作。"
                },
                {
                    "name": "T+19 結算出場",
                    "date": "2026-07-30",
                    "status": "upcoming",
                    "description": "無動作。"
                }
            ],
            "performance": None
        },
        {
            "stock_code": "2467",
            "company_name": "志皓",
            "bond_name": "志皓二",
            "expected_listing_date": "2026-07-02",
            "current_stage_index": 2, # Failed at check
            "status_text": "不符合條件：T-15 籌碼審查不符，已放棄交易",
            "status_type": "failed",
            "strategy_info": {
                "name": "策略 1 & 2: 籌碼卡位型",
                "win_rate": 100.0,
                "avg_return": 45.0
            },
            "stations": [
                {
                    "name": "競拍公告發布",
                    "date": "2026-06-08",
                    "status": "completed",
                    "description": "志皓二競拍時程公告，預定 2026-07-02 掛牌。"
                },
                {
                    "name": "T-15 籌碼審查",
                    "date": "2026-06-11",
                    "status": "failed",
                    "description": "❌ 籌碼不符：外資累計買超僅 120 張，投信 0 張。未達 2,000 張最低門檻且股本佔比未達 0.5%。"
                },
                {
                    "name": "T-14 策略買進",
                    "date": "2026-06-12",
                    "status": "upcoming",
                    "description": "已放棄買進。"
                },
                {
                    "name": "T日 掛牌上市",
                    "date": "2026-07-02",
                    "status": "upcoming",
                    "description": "無持股掛牌。"
                },
                {
                    "name": "T+1~18 拆解拉抬",
                    "date": "2026-07-03",
                    "status": "upcoming",
                    "description": "無動作。"
                },
                {
                    "name": "T+19 結算出場",
                    "date": "2026-07-29",
                    "status": "upcoming",
                    "description": "無動作。"
                }
            ],
            "performance": None
        }
    ]

    os.makedirs(DATA_DIR, exist_ok=True)
    out_path = os.path.join(DATA_DIR, "active_tracks.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(active_tracks, f, ensure_ascii=False, indent=2)
    print(f"Successfully generated active tracking timelines to {out_path}")

if __name__ == "__main__":
    main()
