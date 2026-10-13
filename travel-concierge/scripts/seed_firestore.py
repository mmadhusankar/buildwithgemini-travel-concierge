#!/usr/bin/env python3
"""Seed Firestore with curated travel destinations."""

from google.cloud import firestore

# Hardcoded project ID as string to avoid project number issues on Agent Platform
PROJECT_ID = "qwiklabs-gcp-04-ed27c58745ed"
COLLECTION_NAME = "destinations"

SEED_DESTINATIONS = [
    {
        "id": "kyoto-fushimi-inari",
        "name": "Fushimi Inari-taisha",
        "city": "Kyoto",
        "country": "Japan",
        "category": "Culture & Heritage",
        "description": "Iconic Shinto shrine with thousands of vibrant vermilion torii gates winding up sacred Mount Inari.",
        "estimated_cost_usd": 0.0,
        "recommended_duration_hours": 2.5,
        "rating": 4.8,
        "tags": ["shrine", "hiking", "photography", "free", "historic"],
    },
    {
        "id": "kyoto-arashiyama-bamboo",
        "name": "Arashiyama Bamboo Grove",
        "city": "Kyoto",
        "country": "Japan",
        "category": "Nature",
        "description": "Enchanting path through towering green bamboo stalks that sway and rustle in the gentle mountain breeze.",
        "estimated_cost_usd": 0.0,
        "recommended_duration_hours": 1.5,
        "rating": 4.6,
        "tags": ["nature", "scenic", "photography", "peaceful"],
    },
    {
        "id": "paris-montmartre",
        "name": "Montmartre & Sacré-Cœur",
        "city": "Paris",
        "country": "France",
        "category": "Culture & Arts",
        "description": "Bohemian hilltop district with cobblestone alleys, street artists, and panoramic views of Paris from the basilica.",
        "estimated_cost_usd": 0.0,
        "recommended_duration_hours": 3.0,
        "rating": 4.7,
        "tags": ["art", "scenic-view", "walking", "cafes", "historic"],
    },
    {
        "id": "paris-louvre-museum",
        "name": "Louvre Museum",
        "city": "Paris",
        "country": "France",
        "category": "Museums",
        "description": "The world's largest art museum, home to masterpieces like the Mona Lisa and the Venus de Milo.",
        "estimated_cost_usd": 24.0,
        "recommended_duration_hours": 4.0,
        "rating": 4.8,
        "tags": ["museum", "art", "history", "architecture"],
    },
    {
        "id": "nyc-high-line",
        "name": "The High Line",
        "city": "New York",
        "country": "USA",
        "category": "Urban Scenic",
        "description": "A 1.45-mile elevated rail line turned public park featuring lush landscaping, public art, and Hudson River vistas.",
        "estimated_cost_usd": 0.0,
        "recommended_duration_hours": 1.5,
        "rating": 4.7,
        "tags": ["park", "walking", "skyline", "modern-art"],
    },
    {
        "id": "tokyo-teamlab-planets",
        "name": "teamLab Planets",
        "city": "Tokyo",
        "country": "Japan",
        "category": "Digital Art",
        "description": "Immersive digital art museum where visitors walk through water and interact with kaleidoscopic light installations.",
        "estimated_cost_usd": 28.0,
        "recommended_duration_hours": 2.0,
        "rating": 4.9,
        "tags": ["modern-art", "immersive", "technology", "indoor"],
    },
]


def seed_database():
    db = firestore.Client(project=PROJECT_ID)
    collection = db.collection(COLLECTION_NAME)
    print(f"Seeding '{COLLECTION_NAME}' in project '{PROJECT_ID}'...")

    for item in SEED_DESTINATIONS:
        doc_id = item["id"]
        doc_ref = collection.document(doc_id)
        doc_ref.set(item)
        print(f"  ✓ Added/Updated: {item['name']} ({doc_id})")

    print(f"Done! Successfully seeded {len(SEED_DESTINATIONS)} destinations.")


if __name__ == "__main__":
    seed_database()
