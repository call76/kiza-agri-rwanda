"""Crop catalogue: 6 core crops (db.CROPS) + 100+ more BASELINE crops for Rwanda / East Africa.
EVERY NUMBER HERE IS A BASELINE ESTIMATE from general agronomic knowledge - NOT validated RAB / NISR data. Prices are rough farm-gate RWF/kg, costs are RWF per hectare
for a smallholder, temperature = optimum range in C, rain = mm per WEEK, seasons A/B/C = Rwandan agricultural seasons. Replace with official values on the Data page
(crops CSV upload updates by name). Columns match the crops table / upload template exactly."""
import csv, io

_T = """name,yield_t_ha,price_kg,cost_ha,temp_min,temp_max,rain_min,rain_max,ph_min,ph_max,seasons,water_need,disease_risk,cycle_days
Wheat,2.5,450,600000,10,22,10,40,6.0,7.5,"A,B",Medium,.35,120
Sorghum,2.0,500,450000,20,32,10,40,5.5,7.5,"A,B",Low,.25,120
Finger millet,1.5,700,450000,18,28,10,40,5.0,6.5,"A,B",Low,.25,110
Pearl millet,1.2,600,400000,22,34,8,35,5.5,7.5,"A,B",Low,.20,100
Barley,2.5,450,600000,10,22,10,40,6.0,7.5,"A,B",Medium,.30,110
Oats,2.0,500,550000,10,20,10,40,5.5,7.0,"A,B",Medium,.30,110
Teff,1.2,900,500000,12,26,10,40,5.5,7.0,"A,B",Low,.20,100
Sweet corn,10,300,900000,18,30,15,60,5.8,7.0,"A,B",Medium,.35,90
Quinoa,1.5,2500,500000,12,24,8,30,6.0,7.5,"A,B",Low,.20,110
Soybean,1.5,700,550000,20,30,10,45,6.0,7.0,"A,B",Medium,.30,110
Groundnut,1.2,1500,650000,20,30,10,40,5.8,7.0,"A,B",Medium,.30,120
Pigeon pea,1.0,800,450000,20,32,8,40,5.5,7.0,"A,B",Low,.25,180
Cowpea,1.0,800,400000,22,32,8,40,5.5,7.0,"A,B",Low,.25,90
Green gram,0.8,1100,400000,22,32,8,35,6.0,7.2,"A,B",Low,.25,80
Lentil,0.8,1300,450000,14,25,6,30,6.0,7.5,"A,B",Low,.25,100
Chickpea,1.0,1200,450000,15,26,6,30,6.0,7.5,"A,B",Low,.25,110
Faba bean,2.0,800,550000,12,22,10,40,6.0,7.5,"A,B",Medium,.35,120
Climbing beans,2.5,900,700000,16,26,10,50,5.8,6.8,"A,B",Medium,.35,110
Field peas,1.5,900,500000,12,24,10,40,6.0,7.5,"A,B",Medium,.30,100
Garden peas,6.0,900,1000000,12,22,12,40,6.0,7.5,"A,B,C",Medium,.35,80
Snow peas,6.0,1500,1100000,12,22,12,40,6.0,7.5,"A,B,C",Medium,.35,75
Bambara groundnut,0.8,1200,400000,20,30,8,35,5.5,6.5,"A,B",Low,.20,120
Lablab,1.0,600,350000,20,30,8,35,5.5,7.0,"A,B",Low,.20,150
Green beans,8.0,900,1200000,18,28,12,45,6.0,7.0,"A,B,C",Medium,.40,65
Lupin,1.5,500,400000,12,24,8,35,5.0,7.0,"A,B",Low,.25,150
Sweet potato,12,300,700000,18,30,10,50,5.5,6.5,"A,B,C",Low,.25,120
Orange-fleshed sweet potato,14,350,750000,18,30,10,50,5.5,6.5,"A,B,C",Low,.25,120
Yam,10,600,900000,22,32,15,55,5.5,7.0,"A,B",Medium,.30,240
Taro,10,500,800000,20,30,25,70,5.5,7.0,"A,B",High,.30,210
Cocoyam,8,450,750000,20,30,25,70,5.5,6.5,"A,B",High,.30,240
Arrowroot,8,600,700000,20,30,15,55,5.5,7.0,"A,B",Medium,.20,270
Ginger,10,1500,1800000,20,30,20,60,5.5,6.5,"A,B",Medium,.30,240
Turmeric,8,1200,1500000,20,30,20,60,5.5,7.0,"A,B",Medium,.25,270
Carrot,25,400,1400000,14,24,10,35,6.0,6.8,"A,B,C",Medium,.35,100
Beetroot,20,400,1200000,12,24,10,35,6.0,7.5,"A,B,C",Medium,.30,80
Radish,15,350,700000,12,24,10,35,6.0,7.0,"A,B,C",Medium,.25,35
Turnip,18,300,800000,10,22,10,35,6.0,7.5,"A,B,C",Medium,.25,60
Cabbage,35,250,1800000,12,24,15,45,6.0,7.0,"A,B,C",Medium,.50,90
Chinese cabbage,30,300,1500000,12,24,15,45,6.0,7.0,"A,B,C",Medium,.45,60
Onion,20,700,1800000,13,27,10,35,6.0,7.0,"B,C",Medium,.40,120
Spring onion,12,800,1200000,13,25,10,35,6.0,7.0,"A,B,C",Medium,.35,70
Garlic,8,2000,1800000,12,24,8,30,6.0,7.5,"B,C",Low,.30,150
Leek,20,600,1400000,10,22,10,35,6.0,7.5,"A,B,C",Medium,.30,120
Cauliflower,18,700,1700000,12,22,15,45,6.0,7.0,"A,B,C",Medium,.45,90
Broccoli,12,900,1800000,12,22,15,45,6.0,7.0,"A,B,C",Medium,.45,85
Kale,20,250,1000000,12,24,12,40,6.0,7.0,"A,B,C",Medium,.35,70
Spinach,15,350,900000,12,24,12,40,6.0,7.0,"A,B,C",Medium,.30,45
Amaranth,10,300,600000,18,30,10,40,5.5,7.5,"A,B,C",Medium,.20,40
Lettuce,15,600,1300000,12,22,10,35,6.0,7.0,"A,B,C",Medium,.35,60
Eggplant,20,500,1700000,20,30,15,45,5.5,6.8,"A,B,C",Medium,.45,120
Sweet pepper,20,1200,2500000,18,28,15,45,6.0,6.8,"B,C",Medium,.45,120
Hot pepper,8,1500,1500000,20,30,12,40,6.0,7.0,"A,B,C",Medium,.40,120
Cucumber,25,350,1600000,18,28,15,45,6.0,7.0,"A,B,C",High,.45,65
Zucchini,20,500,1400000,18,28,15,45,6.0,7.0,"A,B,C",Medium,.35,60
Pumpkin,20,250,800000,18,28,12,45,6.0,7.0,"A,B",Medium,.25,110
Butternut,20,400,1000000,18,28,12,45,6.0,7.0,"A,B",Medium,.30,100
Okra,8,600,1000000,22,32,15,45,6.0,7.0,"A,B,C",Medium,.30,70
Celery,25,700,1800000,12,22,15,45,6.0,7.0,"A,B,C",High,.40,110
African nightshade,10,350,600000,18,28,12,40,5.5,7.0,"A,B,C",Medium,.25,45
Cassava leaves,6,400,500000,20,32,10,50,5.0,7.0,"A,B",Low,.25,120
Cherry tomato,20,800,2800000,18,28,15,50,6.0,6.8,"B,C",High,.55,100
Banana (cooking),15,300,1200000,20,30,20,60,5.5,7.0,"A,B,C",High,.40,365
Banana (dessert),20,400,1400000,20,30,20,60,5.5,7.0,"A,B,C",High,.40,365
Avocado,10,600,1500000,16,26,15,50,5.5,7.0,"A,B,C",Medium,.30,1095
Mango,10,400,1200000,22,32,10,40,5.5,7.5,"A,B,C",Low,.30,1460
Pineapple,35,400,2200000,22,30,15,45,4.5,6.5,"A,B,C",Medium,.30,540
Passion fruit,12,1200,2200000,18,28,15,45,5.5,7.0,"A,B,C",Medium,.45,270
Tree tomato,20,1000,1800000,15,24,15,45,5.5,7.0,"A,B,C",Medium,.35,540
Papaya,40,400,2000000,22,32,15,50,5.5,6.8,"A,B,C",Medium,.40,300
Orange,15,500,1600000,18,30,12,45,5.5,7.0,"A,B,C",Medium,.30,1460
Lemon,15,700,1500000,18,30,12,45,5.5,7.0,"A,B,C",Medium,.30,1095
Lime,12,700,1400000,18,30,12,45,5.5,7.0,"A,B,C",Medium,.30,1095
Tangerine,12,600,1500000,18,30,12,45,5.5,7.0,"A,B,C",Medium,.30,1460
Guava,15,500,1000000,20,30,10,45,5.0,7.0,"A,B,C",Low,.25,730
Strawberry,10,2000,3500000,12,24,12,35,5.5,6.5,"A,B,C",Medium,.45,120
Watermelon,25,300,1500000,22,32,10,35,6.0,7.0,"B,C",Medium,.35,90
Melon,20,500,1600000,22,32,10,35,6.0,7.0,"B,C",Medium,.35,90
Apple,10,900,2000000,10,22,12,40,6.0,7.0,"A,B,C",Medium,.40,1825
Macadamia,3,1500,1500000,18,28,15,50,5.0,6.5,"A,B,C",Medium,.20,2190
Jackfruit,15,300,900000,22,32,15,55,5.5,7.0,"A,B,C",Medium,.20,1825
Coffee (Arabica),2.5,500,1600000,15,24,15,45,5.0,6.5,"A,B,C",Medium,.45,1095
Tea (green leaf),6,250,1800000,13,25,25,60,4.5,5.8,"A,B,C",High,.30,1095
Pyrethrum,0.8,1500,1000000,10,20,12,40,5.5,7.0,"A,B,C",Medium,.30,150
Sugarcane,60,60,1500000,20,32,20,60,6.0,7.5,"A,B,C",High,.25,365
Cotton,0.8,700,700000,22,32,10,35,5.5,7.5,"A,B",Low,.35,160
Sunflower,1.5,600,500000,18,30,10,40,6.0,7.5,"A,B",Low,.25,110
Sesame,0.6,1500,400000,22,32,8,30,5.5,7.5,"A,B",Low,.25,100
Canola,1.5,700,550000,10,22,10,35,6.0,7.5,"A,B",Medium,.30,120
Coriander,5,1500,800000,12,24,8,30,6.0,7.5,"A,B,C",Low,.20,60
Basil,8,1500,900000,18,28,10,35,6.0,7.5,"A,B,C",Medium,.25,60
Mint,10,1200,900000,14,26,12,40,6.0,7.5,"A,B,C",Medium,.20,70
Lemongrass,15,500,700000,20,32,12,45,5.5,7.5,"A,B,C",Medium,.15,120
Rosemary,6,2000,900000,12,26,8,30,6.0,7.5,"A,B,C",Low,.15,150
Parsley,10,1500,1000000,12,24,10,35,6.0,7.0,"A,B,C",Medium,.25,75
Thyme,5,2500,900000,12,26,8,30,6.0,7.5,"A,B,C",Low,.15,150
Moringa,10,600,600000,22,34,8,35,6.0,7.5,"A,B,C",Low,.15,180
Napier grass,80,40,500000,20,32,20,60,5.5,7.0,"A,B,C",High,.15,60
Brachiaria,15,50,400000,20,32,15,50,5.5,7.0,"A,B,C",Medium,.15,90
Desmodium,10,80,350000,18,28,15,50,5.5,7.0,"A,B,C",Medium,.15,90
Lucerne,12,100,600000,15,28,10,35,6.5,7.5,"A,B,C",Medium,.25,60
Rhodes grass,12,50,350000,20,32,10,40,6.0,7.5,"A,B",Low,.15,90
Fodder maize,40,60,700000,18,30,15,60,5.5,7.0,"A,B",Medium,.25,90
Calliandra,8,60,300000,18,30,12,45,5.0,7.0,"A,B,C",Low,.10,365
"""

def _rows():
    out = []
    for r in csv.DictReader(io.StringIO(_T)):
        out.append((r["name"], float(r["yield_t_ha"]), float(r["price_kg"]), float(r["cost_ha"]), float(r["temp_min"]), float(r["temp_max"]), float(r["rain_min"]), float(r["rain_max"]),
                    float(r["ph_min"]), float(r["ph_max"]), r["seasons"], r["water_need"], float(r["disease_risk"]), int(r["cycle_days"])))
    return out

EXTRA = _rows()                                    # 100+ baseline crops (the 6 core crops live in db.CROPS)
HEADER = _T.splitlines()[0]
def csv_text(core):
    """Full catalogue as an upload-ready CSV (core crops first)."""
    o = io.StringIO(); w = csv.writer(o, lineterminator="\n"); w.writerow(HEADER.split(","))
    for r in list(core) + EXTRA: w.writerow(r)
    return o.getvalue()

# Nkunganire-style fertilizer placeholders for more crops: crop, stage, fertilizer, kg/ha, open-market RWF/kg, subsidized RWF/kg - DEMO placeholders, pending official approval
FERT_EXTRA = [("Wheat", "planting", "DAP", 100, 1100, 750), ("Wheat", "top_dressing", "Urea", 80, 900, 600), ("Barley", "planting", "DAP", 80, 1100, 750), ("Sorghum", "planting", "DAP", 60, 1100, 750),
 ("Sorghum", "top_dressing", "Urea", 60, 900, 600), ("Soybean", "planting", "NPK 17-17-17", 50, 1000, 700), ("Groundnut", "planting", "DAP", 50, 1100, 750), ("Climbing beans", "planting", "DAP", 60, 1100, 750),
 ("Sweet potato", "planting", "NPK 17-17-17", 100, 1000, 700), ("Garden peas", "planting", "DAP", 100, 1100, 750), ("Onion", "planting", "NPK 17-17-17", 250, 1000, 700), ("Onion", "top_dressing", "Urea", 100, 900, 600),
 ("Cabbage", "planting", "NPK 17-17-17", 250, 1000, 700), ("Cabbage", "top_dressing", "Urea", 150, 900, 600), ("Carrot", "planting", "NPK 17-17-17", 200, 1000, 700),
 ("Banana (cooking)", "planting", "NPK 17-17-17", 200, 1000, 700), ("Coffee (Arabica)", "planting", "NPK 17-17-17", 300, 1000, 700), ("Tea (green leaf)", "planting", "NPK 17-17-17", 300, 1000, 700),
 ("Sunflower", "planting", "DAP", 60, 1100, 750), ("Cherry tomato", "planting", "NPK 17-17-17", 250, 1000, 700), ("Cherry tomato", "top_dressing", "Urea", 100, 900, 600)]
