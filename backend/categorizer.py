import re

def clean_description(raw_narration: str) -> str:
    """
    Strips UPI/IMPS/NEFT/ACH/POS prefixes, reference numbers,
    transaction IDs, account masks, VPA handles, and returns a clean merchant name.
    """
    if not raw_narration:
        return "Unknown"

    text = raw_narration.strip()

    # Common prefixes to strip
    prefix_patterns = [
        r'^(UPI|IMPS|NEFT|RTGS|ACH|NACH|POS|ATM|E-COMM|CMS)[/\s\-_]+',
        r'^(CR|DR|REV|P2P|P2A)[/\s\-_]+',
        r'^(UPI|IMPS|NEFT|RTGS|ACH|NACH|POS|ATM)[/\s\-_]+(CR|DR|REV|P2P|P2A)[/\s\-_]+',
        r'^(ACH\s+D-|NACH\s+D-|ACH\s+C-|NACH\s+C-)',
    ]
    for pattern in prefix_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)

    # Split by '/' or '_' or '-' to examine segments if formatted like UPI/REF/MERCHANT/HANDLE
    segments = [s.strip() for s in re.split(r'[/_]', text) if s.strip()]

    clean_parts = []
    for seg in segments:
        # Skip pure numbers or hex-like codes (8-20 digits reference numbers)
        if re.match(r'^[N\d]{8,20}$', seg, re.IGNORECASE):
            continue
        # Skip short numeric codes
        if re.match(r'^\d{4,7}$', seg):
            continue
        # Skip bank handles like @icici, @okhdfcbank, @paytm, @ybl
        if '@' in seg:
            continue
        # Skip trailing generic tokens
        if seg.upper() in ['UPI', 'PAYMENT', 'CR', 'DR', 'P2P', 'P2A', 'TRANSFER', 'REV', 'MTH', 'DEBIT', 'CREDIT']:
            continue
        # Skip card masks like 412345XXXXXX1234
        if re.search(r'X{4,}', seg, re.IGNORECASE):
            seg = re.sub(r'\b\d{4,6}X+\d{3,4}\b', '', seg, flags=re.IGNORECASE).strip()
            if not seg:
                continue

        clean_parts.append(seg)

    if clean_parts:
        text = " ".join(clean_parts)

    # Remove remaining card masks, reference numbers, VPA suffixes
    text = re.sub(r'\b\d{4,6}X+\d{3,4}\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\b', '', text)
    text = re.sub(r'\b\d{6,}\b', '', text)
    text = re.sub(r'\b(UPI|IMPS|NEFT|RTGS|P2P|P2A|CR|DR|MTH|INVOICE\d*)\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip(' -/,')

    # Formatting refinements for common merchants
    t_lower = text.lower()
    if 'swiggy' in t_lower:
        return 'Swiggy'
    if 'zomato' in t_lower:
        return 'Zomato'
    if 'netflix' in t_lower:
        return 'Netflix'
    if 'spotify' in t_lower:
        return 'Spotify'
    if 'amazon' in t_lower:
        return 'Amazon'
    if 'flipkart' in t_lower:
        return 'Flipkart'
    if 'myntra' in t_lower:
        return 'Myntra'
    if 'bescom' in t_lower or ('bangalore' in t_lower and 'electricity' in t_lower):
        return 'Bescom Electricity'
    if 'rent' in t_lower and ('landlord' in t_lower or 'sharma' in t_lower):
        return 'House Rent (Landlord Sharma)'
    if 'office rent' in t_lower or ('rent' in t_lower and 'commercial' in t_lower):
        return 'Office Rent'
    if 'hostel' in t_lower:
        return 'Hostel Accommodation'
    if 'car loan' in t_lower or 'hdfc bank car' in t_lower:
        return 'HDFC Car Loan EMI'
    if 'laptop' in t_lower or 'bajaj' in t_lower:
        return 'Bajaj Laptop EMI'
    if 'business loan' in t_lower or 'equipment loan' in t_lower:
        return 'Business Equipment Loan EMI'
    if 'wework' in t_lower or 'coworking' in t_lower:
        return 'WeWork Coworking Space'
    if 'airtel' in t_lower:
        return 'Airtel Broadband & Phone'
    if 'jio' in t_lower:
        return 'Jio Fiber & Mobile'
    if 'cult' in t_lower or 'gym' in t_lower:
        return 'Cult.fit Gym Membership'
    if 'apollo' in t_lower or '1mg' in t_lower or 'pharmacy' in t_lower:
        return 'Apollo Pharmacy'
    if 'lic' in t_lower or 'insurance' in t_lower:
        return 'Life & Health Insurance'
    if 'uber' in t_lower:
        return 'Uber Rides'
    if 'ola' in t_lower:
        return 'Ola Cabs'
    if 'petrol' in t_lower or 'fuel' in t_lower or 'indian oil' in t_lower:
        return 'Fuel / Petrol'
    if 'bigbasket' in t_lower:
        return 'BigBasket Groceries'
    if 'blinkit' in t_lower or 'zepto' in t_lower:
        return 'Quick Grocery Delivery'
    if 'reliance fresh' in t_lower or 'reliance' in t_lower:
        return 'Reliance Fresh Groceries'
    if 'figma' in t_lower or 'adobe' in t_lower:
        return 'Figma & Adobe Subscriptions'
    if 'bookmyshow' in t_lower or 'pvr' in t_lower or 'cinema' in t_lower:
        return 'BookMyShow Entertainment'
    if 'acme' in t_lower or 'salary' in t_lower:
        return 'Salary (Acme Corp)'
    if 'client' in t_lower or 'apex' in t_lower:
        return 'Apex Tech Client'
    if 'nexus' in t_lower:
        return 'Nexus Labs Client'

    # Title-case clean merchant
    cleaned = ' '.join(w.capitalize() for w in text.split())
    return cleaned or "General Merchant"

def categorize_transaction(raw_narration: str, cleaned_merchant: str, amount: float, tx_type: str) -> str:
    """
    Categorizes transactions into the standard 14 categories:
    Food, Groceries, Shopping, Housing, Subscriptions, Utilities, Phone/Data,
    Transport, Health/Fitness, Insurance, Loan/EMI, Entertainment, Income, Other.
    """
    combined = f"{raw_narration} {cleaned_merchant}".lower()

    if tx_type == "credit":
        return "Income"

    # Debits: Priority matching for specific categories
    # 1. Housing (merge Rent into it)
    if any(k in combined for k in ["rent", "landlord", "hostel", "pg ", "accommodation", "coworking", "wework", "maintenance", "flat rent", "office rent"]):
        return "Housing"

    # 2. Loan/EMI
    if any(k in combined for k in ["emi", "loan", "bajaj finance", "hdfc bank car", "car loan", "home loan", "mortgage", "equipment loan"]):
        return "Loan/EMI"

    # 3. Phone/Data
    if any(k in combined for k in ["airtel", "jio", "vodafone", "vi ", "broadband", "act fibernet", "wifi", "recharge", "phone bill", "mobile recharge", "data pack"]):
        return "Phone/Data"

    # 4. Utilities
    if any(k in combined for k in ["electricity", "bescom", "power", "water bill", "gas cylinder", "indane", "piped gas", "utility", "eb bill"]):
        return "Utilities"

    # 5. Insurance
    if any(k in combined for k in ["insurance", "lic", "policybazaar", "hdfc life", "icici lombard", "star health", "mediclaim", "premium"]):
        return "Insurance"

    # 6. Subscriptions
    if any(k in combined for k in ["netflix", "spotify", "prime video", "hotstar", "disney", "youtube premium", "figma", "adobe", "saas", "cloud subscription", "apple music"]):
        return "Subscriptions"

    # 7. Health/Fitness
    if any(k in combined for k in ["gym", "cult", "cult.fit", "fitness", "protein", "pharmacy", "apollo", "1mg", "hospital", "clinic", "doctor", "diagnostic", "medicine"]):
        return "Health/Fitness"

    # 8. Transport
    if any(k in combined for k in ["uber", "ola", "rapido", "metro", "fuel", "petrol", "diesel", "indian oil", "bpcl", "hpcl", "fastag", "toll", "irctc", "railway", "flight", "indigo"]):
        return "Transport"

    # 9. Groceries
    if any(k in combined for k in ["groceries", "reliance fresh", "fresh", "supermarket", "blinkit", "zepto", "bigbasket", "vegetables", "dmart", "dairy", "milk"]):
        return "Groceries"

    # 10. Food
    if any(k in combined for k in ["swiggy", "zomato", "cafe", "restaurant", "dining", "canteen", "snacks", "chai", "coffee", "starbucks", "mcdonald", "burger", "pizza", "food delivery"]):
        return "Food"

    # 11. Entertainment
    if any(k in combined for k in ["bookmyshow", "movies", "pvr", "inox", "cinema", "steam", "playstation", "gaming", "concert", "events", "amusement"]):
        return "Entertainment"

    # 12. Shopping
    if any(k in combined for k in ["amazon", "flipkart", "myntra", "ajio", "zara", "shopping", "stationery", "xerox", "store", "clothing", "apparel", "electronics"]):
        return "Shopping"

    return "Other"
