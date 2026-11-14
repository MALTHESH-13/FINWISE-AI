import os
import csv
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

def generate_salaried_data():
    records = []
    # 4 months: Aug, Sep, Oct, Nov 2026
    for month_offset in range(4):
        m_start = datetime(2026, 8 + month_offset, 1)
        m_str = m_start.strftime("%Y-%m")
        
        # 1. Salary Income
        records.append({
            "date": m_start.strftime("%Y-%m-%d"),
            "description": f"NEFT-CR-N{109280 + month_offset}1-SALARY ACME CORP-MTH",
            "amount": 75000.0,
            "type": "credit"
        })
        
        # 2. Housing (Rent) - P1
        records.append({
            "date": (m_start + timedelta(days=4)).strftime("%Y-%m-%d"),
            "description": "UPI/382910482910/DR/RENT TO LANDLORD SHARMA/SBI",
            "amount": 25000.0,
            "type": "debit"
        })
        
        # 3. Loan / EMI - P1
        records.append({
            "date": (m_start + timedelta(days=9)).strftime("%Y-%m-%d"),
            "description": "ACH D-HDFC BANK CAR LOAN EMI-83921",
            "amount": 15000.0,
            "type": "debit"
        })
        
        # 4. Utilities - P1
        records.append({
            "date": (m_start + timedelta(days=14)).strftime("%Y-%m-%d"),
            "description": "UPI/BESCOM BANGALORE ELECTRICITY/392019",
            "amount": 2450.0,
            "type": "debit"
        })
        
        # 5. Phone / Data - P1
        records.append({
            "date": (m_start + timedelta(days=12)).strftime("%Y-%m-%d"),
            "description": "UPI/AIRTEL BROADBAND FIBER BILL/839201",
            "amount": 1199.0,
            "type": "debit"
        })
        
        # 6. Subscriptions - P3
        records.append({
            "date": (m_start + timedelta(days=16)).strftime("%Y-%m-%d"),
            "description": "IMPS-NETFLIX ENTERTAINMENT-928190",
            "amount": 649.0,
            "type": "debit"
        })
        records.append({
            "date": (m_start + timedelta(days=17)).strftime("%Y-%m-%d"),
            "description": "UPI/SPOTIFY INDIA RECURRING/948201",
            "amount": 119.0,
            "type": "debit"
        })
        
        # 7. Health / Fitness - P3
        records.append({
            "date": (m_start + timedelta(days=5)).strftime("%Y-%m-%d"),
            "description": "ACH D-CULT FIT GYM MEMBERSHIP BANGALORE",
            "amount": 1800.0,
            "type": "debit"
        })

        # 8. Transport - P2
        records.append({
            "date": (m_start + timedelta(days=8)).strftime("%Y-%m-%d"),
            "description": "POS 412345XXXXXX9821 INDIAN OIL PETROL PUMP",
            "amount": 2200.0,
            "type": "debit"
        })

        # 9. Groceries - P2
        records.append({
            "date": (m_start + timedelta(days=20)).strftime("%Y-%m-%d"),
            "description": "POS 491820XXXXXX9921 RELIANCE FRESH GROCERIES",
            "amount": 5500.0,
            "type": "debit"
        })

        # 10. Food & Shopping: Overspend specifically in November for MoM check
        if month_offset == 3: # November 2026
            # Shopping: 8500 (limit is 5000 -> over by 3500)
            records.append({
                "date": (m_start + timedelta(days=6)).strftime("%Y-%m-%d"),
                "description": "POS 412345XXXXXX1234 AMAZON INDIA FESTIVE SHOPPING",
                "amount": 8500.0,
                "type": "debit"
            })
            # Food: 9200 (limit is 8000 -> over by 1200)
            records.append({
                "date": (m_start + timedelta(days=10)).strftime("%Y-%m-%d"),
                "description": "UPI/328914829102/CR/Swiggy/swiggy@icici/UPI",
                "amount": 4800.0,
                "type": "debit"
            })
            records.append({
                "date": (m_start + timedelta(days=18)).strftime("%Y-%m-%d"),
                "description": "UPI/DR/481928419284/ZOMATO/zomato@hdfcbank/Payment",
                "amount": 4400.0,
                "type": "debit"
            })
        else:
            # Normal months
            records.append({
                "date": (m_start + timedelta(days=6)).strftime("%Y-%m-%d"),
                "description": "POS 412345XXXXXX1234 AMAZON PAY INDIA MUMBAI",
                "amount": 3200.0,
                "type": "debit"
            })
            records.append({
                "date": (m_start + timedelta(days=11)).strftime("%Y-%m-%d"),
                "description": "UPI/328914829102/CR/Swiggy/swiggy@icici/UPI",
                "amount": 2200.0,
                "type": "debit"
            })
            records.append({
                "date": (m_start + timedelta(days=18)).strftime("%Y-%m-%d"),
                "description": "UPI/DR/481928419284/ZOMATO/zomato@hdfcbank/Payment",
                "amount": 1800.0,
                "type": "debit"
            })

    return sorted(records, key=lambda x: x["date"])

def generate_business_data():
    records = []
    
    # 4 months: Aug, Sep, Oct, Nov 2026
    # August Revenue: 150,000
    records.append({"date": "2026-08-04", "description": "NEFT-CR-N948101-CLIENT APEX TECH DESIGN", "amount": 65000.0, "type": "credit"})
    records.append({"date": "2026-08-16", "description": "IMPS/NEXUS LABS CLIENT CONTRACT/839102", "amount": 55000.0, "type": "credit"})
    records.append({"date": "2026-08-27", "description": "UPI/CR/849201948201/CLIENT SPRINT PAYMENT/HDFC", "amount": 30000.0, "type": "credit"})

    # September Revenue: 160,000
    records.append({"date": "2026-09-05", "description": "NEFT-CR-N948201-TECHFLOW STUDIO-RETAINER", "amount": 70000.0, "type": "credit"})
    records.append({"date": "2026-09-18", "description": "IMPS/CLIENT APEX TECH DESIGN/918203", "amount": 50000.0, "type": "credit"})
    records.append({"date": "2026-09-28", "description": "UPI/CR/992810482910/VENTURE PARTNERS GIG/HDFC", "amount": 40000.0, "type": "credit"})

    # October Revenue: 170,000
    records.append({"date": "2026-10-06", "description": "NEFT-CR-N958202-ENTERPRISE CLIENT OCT", "amount": 80000.0, "type": "credit"})
    records.append({"date": "2026-10-18", "description": "IMPS/NEXUS LABS CLIENT CONTRACT/992810", "amount": 55000.0, "type": "credit"})
    records.append({"date": "2026-10-26", "description": "UPI/CR/839102849102/CREATIVE LABS INVOICE/ICICI", "amount": 35000.0, "type": "credit"})

    # November Revenue: only 35,000 (DIP TRIGGER! Baseline = 160k * 0.85 = 136k)
    records.append({"date": "2026-11-06", "description": "IMPS/SMALL CLIENT RETAINER PARTIAL/102931", "amount": 35000.0, "type": "credit"})

    # Monthly Expenses for all 4 months
    for m in [8, 9, 10, 11]:
        m_str = f"2026-{m:02d}"
        
        # P1 Essentials: Housing, Phone/Data, Loan/EMI, Utilities, Insurance
        records.append({"date": f"{m_str}-03", "description": "UPI/COMMERCIAL OFFICE RENT TO LANDLORD SHARMA", "amount": 35000.0, "type": "debit"})
        records.append({"date": f"{m_str}-08", "description": "ACH D-HDFC BANK BUSINESS EQUIPMENT LOAN EMI", "amount": 15000.0, "type": "debit"})
        records.append({"date": f"{m_str}-10", "description": "UPI/AIRTEL BUSINESS FIBER & PHONE LEASED LINE", "amount": 2500.0, "type": "debit"})
        records.append({"date": f"{m_str}-14", "description": "UPI/BESCOM COMMERCIAL ELECTRICITY BILL", "amount": 4200.0, "type": "debit"})
        records.append({"date": f"{m_str}-15", "description": "ACH D-HDFC ERGO COMMERCIAL FIRE & LIABILITY INSURANCE", "amount": 3000.0, "type": "debit"})

        # P2 Needed: Groceries, Transport/fuel, Health
        records.append({"date": f"{m_str}-09", "description": "POS 412345XXXXXX8192 BIGBASKET OFFICE PANTRY GROCERIES", "amount": 4500.0, "type": "debit"})
        records.append({"date": f"{m_str}-12", "description": "POS 491820XXXXXX1029 BHARAT PETROLEUM FUEL CLIENT VISITS", "amount": 4000.0, "type": "debit"})

        # P3 Cut/Pause Temporarily: Subscriptions, Gym/Fitness, Entertainment, Food delivery, Shopping
        records.append({"date": f"{m_str}-16", "description": "IMPS-NETFLIX ENTERTAINMENT LOUNGE-839102", "amount": 649.0, "type": "debit"})
        records.append({"date": f"{m_str}-17", "description": "UPI/SPOTIFY OFFICE MUSIC RECURRING/948201", "amount": 119.0, "type": "debit"})
        records.append({"date": f"{m_str}-18", "description": "POS 482910XXXXXX8192 FIGMA ADOBE CLOUD SUBSCRIPTION", "amount": 3500.0, "type": "debit"})
        records.append({"date": f"{m_str}-05", "description": "ACH D-CULT FIT CORPORATE GYM MEMBERSHIP", "amount": 2500.0, "type": "debit"})
        records.append({"date": f"{m_str}-11", "description": "UPI/328914829102/CR/Swiggy/swiggy@icici/Food Delivery", "amount": 7500.0, "type": "debit"})
        records.append({"date": f"{m_str}-20", "description": "POS 412345XXXXXX1234 AMAZON OFFICE DECOR & SHOPPING", "amount": 6000.0, "type": "debit"})

    return sorted(records, key=lambda x: x["date"])

def save_csv(filename, records):
    os.makedirs(DATA_DIR, exist_ok=True)
    filepath = os.path.join(DATA_DIR, filename)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "description", "amount", "type"])
        writer.writeheader()
        writer.writerows(records)
    print(f"Saved {len(records)} records to {filepath}")

def generate_all():
    salaried = generate_salaried_data()
    save_csv("sample_salaried.csv", salaried)
    save_csv("sample_transactions.csv", salaried)
    
    business = generate_business_data()
    save_csv("sample_business.csv", business)

    # Clean up legacy files if they exist
    for legacy in ["sample_freelancer.csv", "sample_student.csv"]:
        leg_path = os.path.join(DATA_DIR, legacy)
        if os.path.exists(leg_path):
            try:
                os.remove(leg_path)
                print(f"Removed legacy {legacy}")
            except Exception:
                pass

if __name__ == "__main__":
    generate_all()
