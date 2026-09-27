"""Offline geographic localization for Indian FIRMS detections.

Uses an embedded catalog of major Indian industrial centers, mineral basins,
and district hubs with approximate bounding regions to provide human-readable
location context without external API dependencies or network calls.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

# Representative industrial centers, mining basins, and urban clusters across India
INDIAN_HUBS: list[tuple[str, str, float, float]] = [
    # Gujarat
    ("Surat / Hazira Industrial Belt", "Gujarat", 21.1702, 72.8311),
    ("Ahmedabad Industrial Area", "Gujarat", 23.0225, 72.5714),
    ("Vadodara Petrochemical Hub", "Gujarat", 22.3072, 73.1812),
    ("Jamnagar Refinery Hub", "Gujarat", 22.4707, 70.0577),
    ("Bharuch / Ankleshwar Chemical Zone", "Gujarat", 21.7051, 72.9959),
    ("Kutch / Kandla Port Zone", "Gujarat", 23.0753, 70.1337),
    ("Rajkot Engineering Belt", "Gujarat", 22.3039, 70.8022),
    ("Bhavnagar / Alang Belt", "Gujarat", 21.7645, 72.1519),

    # Maharashtra
    ("Mumbai / Thane Industrial Region", "Maharashtra", 19.0760, 72.8777),
    ("Nagpur Industrial Corridor", "Maharashtra", 21.1458, 79.0882),
    ("Chandrapur Thermal / Mining Hub", "Maharashtra", 19.9615, 79.2961),
    ("Pune / Chakan Automobile Hub", "Maharashtra", 18.5204, 73.8567),
    ("Nashik Industrial Zone", "Maharashtra", 19.9975, 73.7898),
    ("Aurangabad / Jalna Steel Cluster", "Maharashtra", 19.8762, 75.3433),
    ("Solapur Region", "Maharashtra", 17.6599, 75.9064),
    ("Tarapur Atomic / Chemical Zone", "Maharashtra", 19.8500, 72.7000),

    # Chhattisgarh & Central Coalfields
    ("Raipur / Bhilai Steel Complex", "Chhattisgarh", 21.2514, 81.6296),
    ("Korba Coal & Power Basin", "Chhattisgarh", 22.3595, 82.7501),
    ("Raigarh Steel / Power Hub", "Chhattisgarh", 21.8974, 83.3950),
    ("Bilaspur Mining Belt", "Chhattisgarh", 22.0797, 82.1409),

    # Odisha
    ("Rourkela Steel Basin", "Odisha", 22.2604, 84.8536),
    ("Angul / Talcher Energy Hub", "Odisha", 20.8400, 85.1500),
    ("Jharsuguda Industrial Corridor", "Odisha", 21.8550, 84.0080),
    ("Paradeep Port / Petrochemical Zone", "Odisha", 20.3167, 86.6111),
    ("Bhubaneswar / Cuttack Belt", "Odisha", 20.2961, 85.8245),
    ("Jajpur / Kalinganagar Steel City", "Odisha", 20.9500, 85.9000),

    # Jharkhand
    ("Jamshedpur Steel Hub", "Jharkhand", 22.8046, 86.2029),
    ("Bokaro Steel City", "Jharkhand", 23.6693, 86.1511),
    ("Dhanbad / Jharia Coalfields", "Jharkhand", 23.7957, 86.4304),
    ("Ranchi Industrial Area", "Jharkhand", 23.3441, 85.3096),

    # West Bengal
    ("Durgapur / Asansol Industrial Belt", "West Bengal", 23.5204, 87.3119),
    ("Kolkata / Howrah Manufacturing Hub", "West Bengal", 22.5726, 88.3639),
    ("Haldia Petrochemical Complex", "West Bengal", 22.0667, 88.0698),
    ("Siliguri Corridor", "West Bengal", 26.7271, 88.3953),

    # Madhya Pradesh
    ("Singrauli / Waidhan Power Hub", "Madhya Pradesh", 24.2000, 82.6600),
    ("Bhopal / Mandideep Industrial Area", "Madhya Pradesh", 23.2599, 77.4126),
    ("Indore / Pithampur Auto Hub", "Madhya Pradesh", 22.7196, 75.8577),
    ("Gwalior Industrial Area", "Madhya Pradesh", 26.2183, 78.1828),
    ("Jabalpur / Katni Mineral Belt", "Madhya Pradesh", 23.1815, 79.9864),

    # Rajasthan
    ("Kota Industrial Complex", "Rajasthan", 25.2138, 75.8648),
    ("Jaipur Industrial Area", "Rajasthan", 26.9124, 75.7873),
    ("Jodhpur Region", "Rajasthan", 26.2389, 73.0243),
    ("Bhilwara Textile / Mineral Belt", "Rajasthan", 25.3475, 74.6408),
    ("Bhiwadi / Alwar Industrial Area", "Rajasthan", 28.2100, 76.8600),

    # North India (Delhi, Haryana, Punjab, UP)
    ("Delhi / NCR Industrial Region", "Delhi / Haryana", 28.6139, 77.2090),
    ("Gurugram / Manesar Auto Corridor", "Haryana", 28.4595, 77.0266),
    ("Faridabad Industrial Hub", "Haryana", 28.4089, 77.3178),
    ("Panipat Refinery / Textile Belt", "Haryana", 29.3909, 76.9635),
    ("Ludhiana Industrial City", "Punjab", 30.9010, 75.8573),
    ("Bathinda Refinery & Power Hub", "Punjab", 30.2110, 74.9455),
    ("Amritsar Region", "Punjab", 31.6340, 74.8723),
    ("Kanpur Industrial City", "Uttar Pradesh", 26.4499, 80.3319),
    ("Lucknow Region", "Uttar Pradesh", 26.8467, 80.9462),
    ("Varanasi / Mughalsarai Hub", "Uttar Pradesh", 25.3176, 82.9739),
    ("Agra / Mathura Refinery Zone", "Uttar Pradesh", 27.1767, 78.0081),
    ("Noida / Greater Noida Tech Hub", "Uttar Pradesh", 28.5355, 77.3910),

    # Bihar
    ("Patna Region", "Bihar", 25.5941, 85.1376),
    ("Barauni / Begusarai Industrial Area", "Bihar", 25.4200, 85.9800),

    # South India (Andhra, Telangana, Karnataka, Tamil Nadu, Kerala)
    ("Visakhapatnam Steel & Port City", "Andhra Pradesh", 17.6868, 83.2185),
    ("Vijayawada / Guntur Corridor", "Andhra Pradesh", 16.5062, 80.6480),
    ("Hyderabad / Cyberabad Corridor", "Telangana", 17.3850, 78.4867),
    ("Ramagundam Thermal Power Hub", "Telangana", 18.8000, 79.4500),
    ("Bengaluru Tech / Aerospace Hub", "Karnataka", 12.9716, 77.5946),
    ("Bellary / Toranagallu Steel Belt", "Karnataka", 15.1394, 76.9214),
    ("Mangaluru Petrochemical / Port Zone", "Karnataka", 12.9141, 74.8560),
    ("Chennai / Ennore Industrial Corridor", "Tamil Nadu", 13.0827, 80.2707),
    ("Coimbatore Engineering Cluster", "Tamil Nadu", 11.0168, 76.9558),
    ("Tuticorin Port / Thermal Hub", "Tamil Nadu", 8.7642, 78.1348),
    ("Kochi Industrial & Port Area", "Kerala", 9.9312, 76.2673),

    # Northeast
    ("Guwahati Industrial Corridor", "Assam", 26.1445, 91.7362),
    ("Digboi / Tinsukia Oil & Gas Basin", "Assam", 27.3800, 95.6300),
]


def resolve_location_name(lat: float, lon: float) -> str:
    """Return an honest geographic reference for Indian coordinates.

    If within 80 km of a recognized industrial or district hub, labels the area.
    Otherwise, labels the state region with distance to nearest known reference.
    """
    if lat is None or lon is None:
        return "Unknown coordinates"

    best_dist = float("inf")
    best_name = "India"
    best_state = "India"

    for name, state, hlat, hlon in INDIAN_HUBS:
        dlat = (lat - hlat) * 111.0
        dlon = (lon - hlon) * 111.0 * math.cos(math.radians(lat))
        dist = math.sqrt(dlat * dlat + dlon * dlon)
        if dist < best_dist:
            best_dist = dist
            best_name = name
            best_state = state

    if best_dist <= 75.0:
        return f"{best_name}, {best_state}"
    if best_dist <= 180.0:
        return f"{best_state} Region (~{int(best_dist)} km from {best_name})"
    return f"{best_state} Sector ({lat:.2f}° N, {lon:.2f}° E)"
