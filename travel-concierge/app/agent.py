# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
import os
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from .a2ui_utils import a2ui_callback


MODEL = "gemini-3.8-flash"


FIRESTORE_PROJECT_ID = "qwiklabs-gcp-04-ed27c58745ed"
GCS_BUCKET_NAME = "travel-concierge-assets-qwiklabs-gcp-04-ed27c58745ed"
_firestore_client = None


def get_db():
    global _firestore_client
    if _firestore_client is None:
        from google.cloud import firestore
        _firestore_client = firestore.Client(project=FIRESTORE_PROJECT_ID)
    return _firestore_client


def search_destinations(city: str = "", category: str = "", max_results: int = 5) -> list[dict]:
    """Search curated travel destinations from Firestore.

    Args:
        city: Optional city filter (e.g., 'Kyoto', 'Paris', 'Tokyo', 'New York').
        category: Optional category filter (e.g., 'Nature', 'Museums', 'Culture & Heritage').
        max_results: Maximum number of results to return.

    Returns:
        A list of destination dictionaries.
    """
    db = get_db()
    docs = db.collection("destinations").stream()
    results = []
    city_lower = city.lower().strip()
    cat_lower = category.lower().strip()

    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        match = True
        if city_lower and city_lower not in data.get("city", "").lower():
            match = False
        if cat_lower and cat_lower not in data.get("category", "").lower():
            match = False
        if match:
            results.append(data)
            if len(results) >= max_results:
                break
    return results


def get_destination_details(destination_id: str) -> dict:
    """Get detailed information about a destination from Firestore by its document ID.

    Args:
        destination_id: The document ID (e.g. 'kyoto-fushimi-inari', 'paris-louvre-museum').

    Returns:
        The destination record as a dictionary, or an error dictionary if not found.
    """
    db = get_db()
    doc = db.collection("destinations").document(destination_id).get()
    if not doc.exists:
        return {"error": f"Destination with id '{destination_id}' not found."}
    data = doc.to_dict()
    data["id"] = doc.id
    return data


def save_destination(
    name: str,
    city: str,
    country: str,
    category: str,
    description: str,
    estimated_cost_usd: float = 0.0,
    recommended_duration_hours: float = 2.0,
    rating: float = 4.5,
    tags: list[str] = [],
) -> str:
    """Save a new travel destination to the Firestore catalog.

    Args:
        name: Name of the destination or attraction.
        city: City where it is located.
        country: Country where it is located.
        category: Category (e.g., 'Culture & Arts', 'Outdoor Adventures', 'Food & Drink').
        description: Informative summary of the place.
        estimated_cost_usd: Estimated cost in USD (0 for free).
        recommended_duration_hours: Recommended visit duration in hours.
        rating: Rating out of 5.0.
        tags: List of keywords/tags describing the destination.

    Returns:
        A confirmation message with the generated ID.
    """
    db = get_db()
    clean_id = f"{city.lower().replace(' ', '-')}-{name.lower().replace(' ', '-')}"
    doc_data = {
        "id": clean_id,
        "name": name,
        "city": city,
        "country": country,
        "category": category,
        "description": description,
        "estimated_cost_usd": float(estimated_cost_usd),
        "recommended_duration_hours": float(recommended_duration_hours),
        "rating": float(rating),
        "tags": tags,
    }
    db.collection("destinations").document(clean_id).set(doc_data)
    return f"Successfully saved destination '{name}' ({clean_id}) to Firestore."


def add_itinerary_stop(
    day: int,
    destination_name: str,
    city: str,
    activity_notes: str,
    estimated_cost_usd: float = 0.0,
) -> str:
    """Save an activity stop to the traveler's itinerary collection in Firestore.

    Args:
        day: Day number of the itinerary (e.g. 1, 2, 3).
        destination_name: Name of the attraction or activity.
        city: City where this stop occurs.
        activity_notes: Tips, schedule details, or notes for the activity.
        estimated_cost_usd: Estimated budget required in USD.

    Returns:
        A confirmation string with the saved itinerary stop ID.
    """
    db = get_db()
    item_id = f"day-{day}-{destination_name.lower().replace(' ', '-')}"
    itinerary_data = {
        "day": int(day),
        "destination_name": destination_name,
        "city": city,
        "activity_notes": activity_notes,
        "estimated_cost_usd": float(estimated_cost_usd),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    db.collection("itineraries").document(item_id).set(itinerary_data)
    return f"Successfully added Day {day} stop: '{destination_name}' in {city}."


def get_live_weather(city: str) -> dict:
    """Fetch real-time live weather conditions for any city worldwide using Open-Meteo.

    Args:
        city: Name of the destination city (e.g. 'Kyoto', 'Paris', 'Tokyo', 'San Francisco', 'New York').

    Returns:
        A dictionary with live weather information including temperature, conditions, humidity, and wind speed.
    """
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1&language=en&format=json"
        req = urllib.request.Request(geo_url, headers={"User-Agent": "TravelConcierge/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            geo_data = json.loads(resp.read().decode())

        results = geo_data.get("results")
        if not results:
            return {"error": f"Could not find coordinates for city: {city}"}

        loc = results[0]
        lat, lon = loc["latitude"], loc["longitude"]
        city_name = loc.get("name", city)
        country = loc.get("country", "")

        weather_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
            f"&temperature_unit=fahrenheit&wind_speed_unit=mph"
        )
        req2 = urllib.request.Request(weather_url, headers={"User-Agent": "TravelConcierge/1.0"})
        with urllib.request.urlopen(req2, timeout=5) as resp:
            w_data = json.loads(resp.read().decode())

        curr = w_data.get("current", {})
        code = curr.get("weather_code", 0)

        weather_desc = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Foggy",
            51: "Light drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            71: "Slight snow",
            80: "Rain showers",
            95: "Thunderstorm",
        }.get(code, "Clear")

        return {
            "city": city_name,
            "country": country,
            "temperature_f": curr.get("temperature_2m"),
            "condition": weather_desc,
            "humidity_pct": curr.get("relative_humidity_2m"),
            "wind_speed_mph": curr.get("wind_speed_10m"),
        }
    except Exception as e:
        return {"error": f"Failed to retrieve weather for {city}: {str(e)}"}


def convert_currency(amount: float, from_currency: str = "USD", to_currency: str = "EUR") -> dict:
    """Convert an amount from one currency to another using live foreign exchange rates from the Frankfurter API.

    Args:
        amount: The monetary amount to convert (e.g. 100.0).
        from_currency: 3-letter currency code to convert from (e.g. 'USD', 'EUR', 'GBP', 'JPY').
        to_currency: 3-letter currency code to convert to (e.g. 'JPY', 'USD', 'EUR', 'GBP').

    Returns:
        A dictionary with the converted amount, exchange rate, and date.
    """
    try:
        from_curr = from_currency.upper().strip()
        to_curr = to_currency.upper().strip()
        url = f"https://api.frankfurter.dev/v1/latest?amount={float(amount)}&base={from_curr}&symbols={to_curr}"
        req = urllib.request.Request(url, headers={"User-Agent": "TravelConcierge/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        rates = data.get("rates", {})
        converted = rates.get(to_curr)
        if converted is None:
            return {"error": f"Could not find exchange rate from {from_curr} to {to_curr}."}

        rate = converted / float(amount) if amount else 0.0
        return {
            "amount_original": float(amount),
            "from_currency": from_curr,
            "to_currency": to_curr,
            "converted_amount": round(converted, 2),
            "exchange_rate": round(rate, 4),
            "date": data.get("date"),
        }
    except Exception as e:
        return {"error": f"Currency conversion failed: {str(e)}"}


def geocode_address(address: str) -> dict:
    """Convert an address or location name into geographic coordinates using Google Maps Geocoding API.

    Args:
        address: The street address, landmark, or location query (e.g. 'Eiffel Tower, Paris', 'Fushimi Inari, Kyoto').

    Returns:
        A dictionary containing the formatted address, latitude, and longitude.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key or api_key == "PASTE_KEY_HERE":
        return {
            "error": "GOOGLE_MAPS_API_KEY is not set or still set to 'PASTE_KEY_HERE'. Please update your API key in .env."
        }

    try:
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={urllib.parse.quote(address)}&key={api_key}"
        req = urllib.request.Request(url, headers={"User-Agent": "TravelConcierge/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        if data.get("status") != "OK" or not data.get("results"):
            return {
                "error": f"Geocoding failed for '{address}': {data.get('status', 'Unknown error')} - {data.get('error_message', '')}"
            }

        first = data["results"][0]
        loc = first.get("geometry", {}).get("location", {})
        return {
            "address": first.get("formatted_address"),
            "latitude": loc.get("lat"),
            "longitude": loc.get("lng"),
        }
    except Exception as e:
        return {"error": f"Geocoding request failed: {str(e)}"}


def find_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "tourist_attraction",
    radius_meters: float = 1500.0,
    max_results: int = 5,
) -> list[dict]:
    """Find nearby points of interest or establishments using Google Places API (New).

    Args:
        latitude: Center latitude coordinate.
        longitude: Center longitude coordinate.
        place_type: Type of place to search for (e.g. 'tourist_attraction', 'restaurant', 'cafe', 'museum', 'park').
        radius_meters: Search radius in meters around the center (default: 1500.0).
        max_results: Maximum number of places to return (default: 5).

    Returns:
        A list of place dictionaries with name, address, and location coordinates.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key or api_key == "PASTE_KEY_HERE":
        return [{
            "error": "GOOGLE_MAPS_API_KEY is not set or still set to 'PASTE_KEY_HERE'. Please update your API key in .env."
        }]

    try:
        url = "https://places.googleapis.com/v1/places:searchNearby"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
            "User-Agent": "TravelConcierge/1.0",
        }
        payload = {
            "includedTypes": [place_type],
            "maxResultCount": min(max(int(max_results), 1), 20),
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": float(latitude),
                        "longitude": float(longitude),
                    },
                    "radius": float(radius_meters),
                }
            },
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())

        results = []
        for p in data.get("places", []):
            loc = p.get("location", {})
            name = p.get("displayName", {}).get("text", "")
            results.append({
                "name": name,
                "address": p.get("formattedAddress", ""),
                "latitude": loc.get("latitude"),
                "longitude": loc.get("longitude"),
            })
        return results
    except Exception as e:
        return [{"error": f"Places search failed: {str(e)}"}]


async def generate_destination_postcard(
    destination_name: str,
    visual_description: str = "",
    tool_context: ToolContext = None,
) -> dict:
    """Generate a scenic travel postcard image for a destination using gemini-3.1-flash-lite-image in global region.

    Saves the generated image to Playground Artifacts and uploads image bytes to public Cloud Storage,
    returning its public HTTPS URL without writing to a local file.

    Args:
        destination_name: Name of the destination, landmark, or city (e.g. 'Arashiyama Bamboo Grove, Kyoto', 'Eiffel Tower').
        visual_description: Optional stylistic or aesthetic details (e.g. 'sunrise lighting, misty morning, scenic postcard').

    Returns:
        A dictionary containing the public Cloud Storage URL and generated image details.
    """
    from google import genai
    from google.cloud import storage

    prompt = f"A scenic travel postcard of {destination_name}. {visual_description}".strip()
    try:
        genai_client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="global")
        resp = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
        )

        image_bytes = None
        if resp.candidates and resp.candidates[0].content and resp.candidates[0].content.parts:
            for part in resp.candidates[0].content.parts:
                if part.inline_data and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    break

        if not image_bytes:
            return {"error": "Image generation model did not return image bytes."}

        safe_name = "".join(c if c.isalnum() else "_" for c in destination_name.lower()).strip("_")
        timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        filename = f"postcard_{safe_name}_{timestamp}.jpg"

        # 1. Save artifact to ToolContext so it shows up in Playground's Artifacts panel
        if tool_context is not None:
            try:
                artifact_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
                await tool_context.save_artifact(filename=filename, artifact=artifact_part)
            except Exception:
                pass

        # 2. Upload image bytes directly to public Cloud Storage bucket
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type="image/jpeg")

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"

        return {
            "status": "success",
            "destination": destination_name,
            "filename": filename,
            "public_url": public_url,
            "message": f"Generated postcard for '{destination_name}' and uploaded to public Cloud Storage.",
        }
    except Exception as e:
        return {"error": f"Failed to generate destination image: {str(e)}"}


async def generate_destination_video(
    destination_name: str,
    scene_description: str = "",
    tool_context: ToolContext = None,
) -> dict:
    """Generate a short scenic travel video for a destination using Google's Omni model (gemini-omni-flash-preview) in global region.

    Saves the generated video to Playground Artifacts and uploads video bytes to public Cloud Storage,
    returning its public HTTPS URL without writing to a local file.

    Args:
        destination_name: Name of the destination, landmark, or city (e.g. 'Arashiyama Bamboo Grove, Kyoto', 'Eiffel Tower', 'Waikiki Beach').
        scene_description: Optional stylistic or visual scene details (e.g. 'gentle ocean waves under golden hour sunset').

    Returns:
        A dictionary containing the public Cloud Storage URL and generated video details.
    """
    import base64
    from google import genai
    from google.cloud import storage

    prompt = f"A short scenic travel video of {destination_name}. {scene_description}".strip()
    bucket_name = "travel-concierge-assets-qwiklabs-gcp-04-ed27c58745ed"
    try:
        genai_client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="global")
        resp = genai_client.interactions.create(
            model="gemini-omni-flash-preview",
            input=[{"type": "text", "text": prompt}],
            response_format=[{"type": "video", "aspect_ratio": "16:9", "duration": "3s"}],
        )

        video_bytes = None
        output_video = getattr(resp, "output_video", None)
        if output_video and getattr(output_video, "data", None):
            data = output_video.data
            if isinstance(data, str):
                video_bytes = base64.b64decode(data)
            elif isinstance(data, (bytes, bytearray)):
                video_bytes = bytes(data)

        if not video_bytes and hasattr(resp, "steps") and resp.steps:
            for step in resp.steps:
                if getattr(step, "type", None) == "model_output":
                    content = getattr(step, "content", []) or []
                    for item in content:
                        if getattr(item, "type", None) == "video" and getattr(item, "data", None):
                            data = item.data
                            if isinstance(data, str):
                                video_bytes = base64.b64decode(data)
                            elif isinstance(data, (bytes, bytearray)):
                                video_bytes = bytes(data)
                            break
                    if video_bytes:
                        break

        if not video_bytes:
            return {"error": "Video generation model did not return video bytes."}

        safe_name = "".join(c if c.isalnum() else "_" for c in destination_name.lower()).strip("_")
        timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        filename = f"video_{safe_name}_{timestamp}.mp4"

        # 1. Save artifact to ToolContext so it shows up in Playground's Artifacts panel
        if tool_context is not None:
            try:
                artifact_part = types.Part.from_bytes(data=video_bytes, mime_type="video/mp4")
                await tool_context.save_artifact(filename=filename, artifact=artifact_part)
            except Exception:
                pass

        # 2. Upload video bytes directly to public Cloud Storage bucket
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type="video/mp4")

        public_url = f"https://storage.googleapis.com/{bucket_name}/{filename}"

        return {
            "status": "success",
            "destination": destination_name,
            "filename": filename,
            "public_url": public_url,
            "message": f"Generated short video for '{destination_name}' and uploaded to public Cloud Storage.",
        }
    except Exception as e:
        return {"error": f"Failed to generate destination video: {str(e)}"}



def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    q = query.lower()
    if "sf" in q or "san francisco" in q:
        tz_identifier = "America/Los_Angeles"
    elif "paris" in q:
        tz_identifier = "Europe/Paris"
    elif "tokyo" in q or "kyoto" in q:
        tz_identifier = "Asia/Tokyo"
    elif "nyc" in q or "new york" in q:
        tz_identifier = "America/New_York"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


SANDBOX_RESOURCE_NAME = (
    "projects/214675179910/locations/us-central1/reasoningEngines/5461784703436587008/sandboxEnvironments/1584257167404302336"
)
AGENT_ENGINE_RESOURCE_NAME = (
    "projects/214675179910/locations/us-central1/reasoningEngines/5461784703436587008"
)

sandbox_executor = AgentEngineSandboxCodeExecutor(
    sandbox_resource_name=SANDBOX_RESOURCE_NAME,
    agent_engine_resource_name=AGENT_ENGINE_RESOURCE_NAME,
)


# WRITE: after each turn, send the session to Memory Bank for extraction.
async def generate_memories_callback(callback_context: CallbackContext):
    await callback_context.add_session_to_memory()
    return None


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are Travel Concierge, a helpful AI travel assistant designed to help travelers discover "
        "curated destinations, check real-time live weather conditions, convert foreign currencies, "
        "geocode addresses, discover nearby attractions, generate scenic destination postcards, "
        "generate short destination travel videos with Google Omni model, "
        "perform complex travel budget and itinerary calculations with Python code execution, "
        "manage itineraries, and save new travel spots. "
        "You remember the user's stated travel preferences, dietary restrictions, favorite spots, and facts from "
        "previous conversations and use them to personalize your recommendations. "
        "CRITICAL: Always remember, track, and strictly respect all user allergies (food, environmental, drug/medical) "
        "across conversations. Whenever recommending dining, food, local delicacies, or activities, review remembered allergies "
        "and proactively verify safety or highlight potential allergens. "
        "Use your tools (PreloadMemoryTool, search_destinations, get_destination_details, save_destination, "
        "add_itinerary_stop, get_live_weather, convert_currency, geocode_address, find_nearby_places, "
        "generate_destination_postcard, generate_destination_video) to ground your recommendations in real data. "
        "When calculating budgets, splits, multi-currency costs, or complex schedules, use your Python code executor sandbox."
    ),
    workflow_description="Analyze the request, call relevant tools to fetch real travel data, and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    code_executor=sandbox_executor,
    tools=[
        PreloadMemoryTool(),
        search_destinations,
        get_destination_details,
        save_destination,
        add_itinerary_stop,
        get_live_weather,
        convert_currency,
        geocode_address,
        find_nearby_places,
        generate_destination_postcard,
        generate_destination_video,
        get_current_time,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)

