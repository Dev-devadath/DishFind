from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from apify_client import ApifyClient
import os
from dotenv import load_dotenv
import google.generativeai as genai
import json
import urllib.parse
import re
from typing import Dict, Optional
import uuid
import asyncio
import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, validator
from typing import Dict, Optional, Union
import math  # Add this import for math.isnan()

# Load environment variables
load_dotenv()

# Configure Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.0-flash')

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RestaurantURL(BaseModel):
    url: str

class TaskStatus(BaseModel):
    state: str
    result: Optional[dict] = None

# Store for task states
tasks: Dict[str, TaskStatus] = {}

# Update the DishSearchRequest model to include optional lat/long with proper defaults
# Update the DishSearchRequest model with proper validators
class DishSearchRequest(BaseModel):
    dish: str
    location: str
    radius: Optional[Union[int, float]] = 10  # Default to 10 if not provided
    latitude: Optional[Union[float, str]] = None
    longitude: Optional[Union[float, str]] = None
    useGeolocation: Optional[bool] = False
    
    @validator('radius')
    def validate_radius(cls, v):
        # Always return a valid number, never None
        if v is None:
            return 10
        try:
            radius = float(v)
            # Ensure radius is at least 1 and not NaN
            if math.isnan(radius) or radius <= 0:
                return 10
            return radius
        except (ValueError, TypeError):
            return 10
            
    @validator('latitude', 'longitude')
    def validate_coordinates(cls, v):
        if v is None:
            return 0.0
        try:
            return float(v)
        except (ValueError, TypeError):
            return 0.0

def extract_restaurant_name_from_url(url: str) -> str:
    try:
        # If it's a search URL, extract the name from the search query
        if "maps/search/" in url:
            # Split the URL by 'search/' and take everything after it
            search_part = url.split('search/')[1]
            # URL decode the search query
            search_query = urllib.parse.unquote(search_part)
            # Clean up the name by removing dots and extra spaces
            search_query = search_query.replace('.', ' ').replace('  ', ' ').strip()
            # Clean up URL-encoded characters and common separators
            search_query = clean_restaurant_name(search_query)
            return search_query

        # For regular Maps URLs
        parsed_url = urllib.parse.urlparse(url)
        path_parts = parsed_url.path.split('/')
        
        # Find the part that comes after 'place' in the URL
        if 'place' in path_parts:
            place_index = path_parts.index('place')
            if len(path_parts) > place_index + 1:
                # Get the next part after 'place' and replace '+' with spaces
                restaurant_name = path_parts[place_index + 1].replace('+', ' ')
                # Remove any location coordinates or other data after '@'
                restaurant_name = restaurant_name.split('@')[0]
                # Clean up the name
                restaurant_name = restaurant_name.replace('.', ' ').replace('  ', ' ').strip()
                # Clean up URL-encoded characters and common separators
                restaurant_name = clean_restaurant_name(restaurant_name)
                return restaurant_name
        
        return "Unknown Restaurant"
    except Exception as e:
        print(f"Error extracting restaurant name: {str(e)}")
        return "Unknown Restaurant"

def clean_restaurant_name(name: str) -> str:
    """Clean up restaurant name by removing URL-encoded characters and common separators."""
    # URL decode the name to handle %xx encoded characters
    try:
        # Apply URL decoding multiple times to handle double-encoded characters
        decoded_name = name
        for _ in range(2):  # Try decoding twice to handle double encoding
            decoded_name = urllib.parse.unquote(decoded_name)
        name = decoded_name
    except Exception as e:
        print(f"Error decoding URL: {str(e)}")
    
    # Replace common separators with a space
    for separator in ['|', '-', '/', '\\', ':', ';', ',']:
        name = name.replace(separator, ' ')
    
    # Remove common suffixes that might appear in restaurant names
    suffixes_to_remove = [
        "restaurant", "Restaurant", 
        "Google Maps", "google maps",
        "Menu", "menu", "Official", "official",
        "Website", "website"
    ]
    
    for suffix in suffixes_to_remove:
        if name.endswith(' ' + suffix):
            name = name[:-len(' ' + suffix)].strip()
    
    # Remove extra spaces
    while '  ' in name:
        name = name.replace('  ', ' ')
    
    return name.strip()

def analyze_reviews_with_gemini(reviews, restaurant_name):
    # Prepare the reviews text
    reviews_text = "\n".join([
        f"Review {i+1} ({review['stars']} stars): {review['text']}"
        for i, review in enumerate(reviews)
    ])
    
    # Create a detailed prompt for Gemini
    prompt = f"""You are a food critic and restaurant analyst. Analyze these reviews for {restaurant_name} and provide a focused analysis of the top 5 best dishes mentioned.

Reviews:
{reviews_text}

Please provide your analysis in the following JSON format:
{{
    "top_dishes": [
        {{
            "name": "dish name",
            "description": "brief description of the dish",
            "recommended_with": "any specific dish or item it's recommended to be served with (if mentioned)",
            "key_points": ["2-3 key positive points about this dish"]
        }}
    ],
    "best_dish": {{
        "name": "name of the best overall dish",
        "description": "brief description of why this is considered the best",
        "recommended_with": "any specific dish or item it's recommended to be served with",
        "key_points": ["2-3 key positive points about this dish"]
    }},
    "summary": "a brief 2-3 sentence summary of the restaurant's strengths and most praised dishes"
}}

Focus on:
1. Most frequently praised dishes
2. Dishes with specific positive mentions
3. Dishes that are recommended to be served together
4. Dishes that stand out in the reviews

Please be concise and focus on the most important information. Return only the JSON object without any markdown formatting or code block markers."""

    try:
        response = model.generate_content(prompt)
        # Clean up the response text by removing markdown code block markers
        response_text = response.text.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        # Try to parse the response as JSON
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            # If JSON parsing fails, return a structured error response
            return {
                "error": "Failed to parse Gemini response as JSON",
                "raw_response": response.text
            }
    except Exception as e:
        return {"error": f"Failed to analyze reviews: {str(e)}"}

def expand_short_url(url: str) -> str:
    try:
        # Check if it's a shortened URL
        if not ("maps.app.goo.gl" in url or "goo.gl/maps" in url or "g.co/kgs/" in url):
            return url

        # Make a request to the shortened URL
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, allow_redirects=True, headers=headers)
        
        # Try to get the final URL from the response
        final_url = response.url
        
        # If we got a valid Google Maps URL, return it
        if "google.com/maps" in final_url:
            return final_url
            
        # If we got redirected to a Google Search page
        if "google.com/search" in final_url:
            # Extract the restaurant name from the search query
            parsed_url = urllib.parse.urlparse(final_url)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            
            # Try to get the restaurant name from different possible parameters
            restaurant_name = None
            
            # First try to get from the search query
            if 'q' in query_params:
                restaurant_name = query_params['q'][0]
            
            # If no name found, try to get from the HTML
            if not restaurant_name:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Try to find the name in the title
                title_elem = soup.find('title')
                if title_elem:
                    # Usually the title is in format "Restaurant Name - Google Search"
                    title_text = title_elem.text
                    if ' - ' in title_text:
                        restaurant_name = title_text.split(' - ')[0]
                
                # If still no name, try to find it in the search results
                if not restaurant_name:
                    # Look for the first search result heading
                    search_result = soup.find('h3')
                    if search_result:
                        restaurant_name = search_result.text.strip()
            
            if restaurant_name:
                # Clean up the restaurant name
                restaurant_name = restaurant_name.replace(' - Google Search', '')
                restaurant_name = restaurant_name.replace(' - Google Maps', '')
                restaurant_name = restaurant_name.strip()
                
                # Create a Google Maps search URL
                search_url = f"https://www.google.com/maps/search/{urllib.parse.quote(restaurant_name)}"
                return search_url
        
        # If not a search page, try to extract from the HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for various patterns in the HTML
        patterns = [
            r'https://www\.google\.com/maps/place/[^"\'<>]+',
            r'https://maps\.google\.com/maps/place/[^"\'<>]+',
            r'data-url="([^"]*maps\.google\.com[^"]*)"',
            r'href="([^"]*maps\.google\.com[^"]*)"',
            r'window\.location\.href\s*=\s*[\'"]([^\'"]+)[\'"]',
            r'data-href="([^"]*maps\.google\.com[^"]*)"',
            r'data-google-maps-url="([^"]*maps\.google\.com[^"]*)"',
            r'data-place-url="([^"]*maps\.google\.com[^"]*)"'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, response.text)
            if matches:
                # If it's a capture group, use the first match
                found_url = matches[0] if isinstance(matches[0], str) else matches[0][0]
                if "google.com/maps" in found_url:
                    return found_url
        
        # If we still haven't found a valid URL, try to find it in meta tags
        meta_tags = soup.find_all('meta', property=['og:url', 'twitter:url'])
        for tag in meta_tags:
            content = tag.get('content', '')
            if "google.com/maps" in content:
                return content
                
        # Try to find the URL in script tags
        script_tags = soup.find_all('script')
        for script in script_tags:
            if script.string and "google.com/maps" in script.string:
                matches = re.findall(r'https://www\.google\.com/maps/place/[^"\'<>]+', script.string)
                if matches:
                    return matches[0]
                
        raise ValueError("Could not extract full Google Maps URL from shortened link")
    except Exception as e:
        print(f"Error expanding URL: {str(e)}")
        raise ValueError(f"Failed to process shortened URL: {str(e)}")

async def process_restaurant_data(task_id: str, url: str):
    try:
        # Update task status to fetching
        tasks[task_id].state = "FETCHING"
        
        # Expand shortened URL if necessary
        try:
            expanded_url = expand_short_url(url)
        except Exception as e:
            tasks[task_id].state = "FAILED"
            tasks[task_id].result = {"error": str(e)}
            return

        # Initialize the ApifyClient with your API token
        client = ApifyClient(os.getenv("APIFY_API_TOKEN"))

        # Try to get restaurant name from URL first
        restaurant_name = extract_restaurant_name_from_url(expanded_url)
        if not restaurant_name:
            restaurant_name = "Unknown Restaurant"

        # Prepare the Actor input
        run_input = {
            "startUrls": [{"url": expanded_url}],
            "maxReviews": 25,
            "reviewsSort": "highestRanking",
            "scrapeReviewsPersonalData": False,
            "language": "en"
        }

        # Run the Actor and wait for it to finish
        run = client.actor("compass/crawler-google-places").call(run_input=run_input)

        # Update task status to analyzing
        tasks[task_id].state = "ANALYZING"

        # Fetch results from the run's dataset
        reviews = []
        
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            if "reviews" in item:
                # Process each review to extract only text and stars
                processed_reviews = []
                for review in item["reviews"]:
                    processed_review = {
                        "text": review.get("text", ""),
                        "stars": review.get("stars", 0)
                    }
                    processed_reviews.append(processed_review)
                reviews.extend(processed_reviews)
            
            # Update restaurant name if available from the API response
            if "name" in item and item["name"]:
                restaurant_name = item["name"]

        # Get the top 10 reviews
        top_reviews = reviews[:10]
        
        # Update task status to finalizing
        tasks[task_id].state = "FINALIZING"
        
        # Analyze reviews with Gemini
        analysis = analyze_reviews_with_gemini(top_reviews, restaurant_name)

        # Store the final result
        result = {
            "success": True,
            "restaurant_name": restaurant_name,
            "reviews": top_reviews,
            "analysis": analysis
        }
        
        tasks[task_id].state = "COMPLETED"
        tasks[task_id].result = result

    except Exception as e:
        tasks[task_id].state = "FAILED"
        tasks[task_id].result = {"error": str(e)}

@app.post("/api/scrape-reviews")
async def scrape_reviews(restaurant: RestaurantURL):
    try:
        # Generate a unique task ID
        task_id = str(uuid.uuid4())
        
        # Initialize task status
        tasks[task_id] = TaskStatus(state="INITIALIZED")
        
        # Start processing in the background
        asyncio.create_task(process_restaurant_data(task_id, restaurant.url))
        
        return {"task_id": task_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return tasks[task_id]

@app.get("/wake")
async def wake_up():
    return {"message": "I Won't Sleep"}

async def analyze_restaurant_for_dish_detailed(restaurant, dish_name):
    """
    Perform a detailed analysis of a restaurant for a specific dish using Gemini API.
    """
    # Pre-aggregate the reviews
    reviews_text = "\n".join([
        f"Review {i+1} ({review['stars']} stars): {review['text']}"
        for i, review in enumerate(restaurant["reviews"]) if review["text"]
    ])
    
    # Create a detailed prompt for Gemini
    prompt = f"""You are a food critic specializing in {dish_name}. Analyze these reviews for {restaurant["name"]} and determine if they serve good {dish_name}.

Restaurant Information:
- Name: {restaurant["name"]}
- Address: {restaurant["address"]}
- Overall Rating: {restaurant["rating"]} stars (from {restaurant["reviewsCount"]} reviews)

Reviews:
{reviews_text}

Please provide your analysis in the following JSON format:
{{
    "serves_dish": true/false,
    "dish_quality": "excellent/good/average/poor/unknown",
    "dish_description": "brief description of how the {dish_name} is prepared or what makes it special at this restaurant",
    "key_points": ["2-3 key points about the {dish_name} at this restaurant"],
    "recommendation": "a brief 1-2 sentence recommendation about the {dish_name} at this restaurant",
    "recommendation_score": a number from 0 to 10 indicating how strongly you recommend this restaurant for {dish_name}
}}

If the reviews don't mention {dish_name} specifically, use your judgment based on the overall restaurant quality, cuisine type, and menu items mentioned to determine if they likely serve good {dish_name}.

Focus on:
1. Quality of the {dish_name} specifically
2. Unique preparation methods or ingredients
3. Consistency in positive reviews about the {dish_name}
4. Overall dining experience related to {dish_name}

Return only the JSON object without any markdown formatting or code block markers."""

    try:
        response = model.generate_content(prompt)
        # Clean up the response text
        response_text = response.text.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        # Try to parse the response as JSON
        try:
            analysis = json.loads(response_text)
            
            # Calculate an AI score based on the recommendation_score and dish_quality
            ai_score = analysis.get("recommendation_score", 0)
            
            # If recommendation_score is not provided, derive it from dish_quality
            if ai_score == 0:
                quality_map = {
                    "excellent": 9.0,
                    "good": 7.0,
                    "average": 5.0,
                    "poor": 3.0,
                    "unknown": 4.0
                }
                ai_score = quality_map.get(analysis.get("dish_quality", "unknown"), 4.0)
            
            # Adjust score based on whether the restaurant serves the dish
            if not analysis.get("serves_dish", False):
                ai_score *= 0.5
            
            # Create the final restaurant object with analysis
            result = {
                "name": restaurant["name"],
                "address": restaurant["address"],
                "rating": restaurant["rating"],
                "reviewsCount": restaurant["reviewsCount"],
                "url": restaurant["url"],
                "reviews": restaurant["reviews"],
                "analysis": analysis,
                "ai_score": ai_score
            }
            
            # Remove logging statement
            return result
            
        except json.JSONDecodeError:
            # Remove logging statement
            return {
                "name": restaurant["name"],
                "address": restaurant["address"],
                "rating": restaurant["rating"],
                "reviewsCount": restaurant["reviewsCount"],
                "url": restaurant["url"],
                "reviews": restaurant["reviews"],
                "analysis": {
                    "serves_dish": False,
                    "dish_quality": "unknown",
                    "dish_description": f"We couldn't determine if this restaurant serves {dish_name}.",
                    "key_points": [],
                    "recommendation": f"This restaurant may serve {dish_name} but we couldn't analyze the quality.",
                    "recommendation_score": 3
                },
                "ai_score": 3.0
            }
    except Exception as e:
        # Remove logging statement
        return {
            "name": restaurant["name"],
            "address": restaurant["address"],
            "rating": restaurant["rating"],
            "reviewsCount": restaurant.get("reviewsCount", 0),
            "url": restaurant["url"],
            "reviews": restaurant["reviews"],
            "analysis": {
                "serves_dish": False,
                "dish_quality": "unknown",
                "dish_description": f"Error analyzing this restaurant for {dish_name}.",
                "key_points": [],
                "recommendation": f"This restaurant may serve {dish_name} but we couldn't analyze the quality.",
                "recommendation_score": 2
            },
            "ai_score": 2.0
        }

async def process_dish_search(task_id: str, search_request: DishSearchRequest):
    try:
        # Update task status to fetching
        tasks[task_id].state = "FETCHING"
        
        # Initialize the ApifyClient with your API token
        client = ApifyClient(os.getenv("APIFY_API_TOKEN"))
        
        # Construct the search query
        search_query = f"{search_request.dish} Restaurants"
        
        # Prepare the Actor input for initial search
        run_input = {
            "searchStringsArray": [search_query],
            "locationQuery": search_request.location,
            "maxCrawledPlacesPerSearch": 20,  # Limit to top 20 places for initial search
            "maxReviews": 10,
            "reviewsSort": "highestRanking",
            "scrapeReviewsPersonalData": False,
            "language": "en"
        }
        
        # Explicitly handle geolocation data with strict None checks and safe conversions
        try:
            # First check if latitude and longitude are not None
            if search_request.latitude is not None and search_request.longitude is not None:
                # Convert to float with explicit error handling
                try:
                    lat = float(search_request.latitude)
                    lng = float(search_request.longitude)
                    
                    # Only add geolocation if conversion was successful and values are valid
                    if not (math.isnan(lat) or math.isnan(lng)):
                        run_input["customGeolocation"] = {
                            "type": "Point",
                            "coordinates": [lng, lat]
                        }
                        
                        # Handle radius with explicit None check and safe conversion
                        radius_meters = 10000  # Default 10km
                        if search_request.radius is not None:
                            try:
                                # Convert to float first to handle both string and numeric inputs
                                radius_value = float(search_request.radius)
                                # Only compare if radius_value is not None
                                if radius_value is not None and radius_value > 0 and not math.isnan(radius_value):
                                    radius_meters = int(radius_value * 1000)
                            except (ValueError, TypeError):
                                # Use default if conversion fails
                                print("Failed to convert radius to float, using default")
                        
                        run_input["searchRadius"] = radius_meters
                except (ValueError, TypeError):
                    print("Failed to convert latitude/longitude to float")
        except Exception as geo_error:
            print(f"Error handling geolocation: {str(geo_error)}")
            # Continue without geolocation if there's an error
        
        # Run the Actor and wait for it to finish
        run = client.actor("compass/crawler-google-places").call(run_input=run_input)
        
        # Update task status to processing
        tasks[task_id].state = "PROCESSING"
        
        # Fetch results from the run's dataset
        restaurants = []
        
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            # Check if this is a restaurant item (has title field)
            if "title" in item:
                # Process each restaurant
                restaurant = {
                    "name": item.get("title", ""),
                    "address": f"{item.get('street', '')}, {item.get('city', '')}, {item.get('state', '')}",
                    "rating": item.get("totalScore", 0),
                    "reviewsCount": item.get("reviewsCount", 0),
                    "url": item.get("url", ""),
                    "reviews": []
                }
                
                # Process reviews if they exist in the same item
                if "reviews" in item:
                    for review in item.get("reviews", [])[:10]:  # Limit to top 10 reviews
                        # Ensure text is not None
                        review_text = review.get("text", "")
                        if review_text is None:
                            review_text = ""
                            
                        processed_review = {
                            "text": review_text,
                            "stars": review.get("stars", 0)
                        }
                        restaurant["reviews"].append(processed_review)
                
                restaurants.append(restaurant)
        
        # If we don't have reviews in the same items, we need to fetch them separately
        # This is a common pattern with the Apify Google Places crawler
        if restaurants and all(len(restaurant["reviews"]) == 0 for restaurant in restaurants):
            # Remove logging statement
            
            # Create a dictionary to map restaurant titles to their objects
            restaurant_map = {restaurant["name"]: restaurant for restaurant in restaurants}
            
            # Go through the dataset again to find review items
            for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                if "text" in item and "title" in item and item["title"] in restaurant_map:
                    restaurant_name = item["title"]
                    # Ensure text is not None
                    review_text = item.get("text", "")
                    if review_text is None:
                        review_text = ""
                        
                    processed_review = {
                        "text": review_text,
                        "stars": item.get("stars", 0)
                    }
                    restaurant_map[restaurant_name]["reviews"].append(processed_review)
        
        # Remove logging statement about found restaurants
        
        # Step 2: Preliminary Filtering
        
        # 1. Basic Ranking by Ratings
        # Sort restaurants by rating (highest first)
        restaurants.sort(key=lambda x: x["rating"], reverse=True)
        
        # 2. Keyword Check on Reviews
        dish_name = search_request.dish.lower()
        # Create a list of possible variations/synonyms of the dish name
        dish_keywords = [dish_name]
        # Remove plurals if present or add them if not
        if dish_name.endswith('s'):
            dish_keywords.append(dish_name[:-1])  # Remove 's' at the end
        else:
            dish_keywords.append(dish_name + 's')  # Add 's' at the end
            
        # Add the singular word if the dish name has multiple words
        if ' ' in dish_name:
            main_word = dish_name.split(' ')[0]
            dish_keywords.append(main_word)
        
        
        # Calculate keyword frequency for each restaurant
        for restaurant in restaurants:
            # Initialize keyword count
            restaurant["keyword_count"] = 0
            
            # Check each review for keywords
            # Ensure we're only joining non-None values
            all_review_text = ' '.join([review["text"].lower() for review in restaurant["reviews"] if review["text"]])
            
            # Count occurrences of each keyword
            for keyword in dish_keywords:
                # Count whole word matches only
                restaurant["keyword_count"] += len(re.findall(r'\b' + re.escape(keyword) + r'\b', all_review_text))
            
            # Calculate a combined score (rating * (1 + keyword_count/10))
            # This gives weight to both the rating and the keyword frequency
            restaurant["combined_score"] = restaurant["rating"] * (1 + restaurant["keyword_count"] / 10)
            
        
        # 3. Select Top Candidates
        # Sort by the combined score
        restaurants.sort(key=lambda x: x["combined_score"], reverse=True)
        
        # Take top 10 restaurants
        top_restaurants = restaurants[:10] if len(restaurants) > 10 else restaurants
        
        # Remove logging of top 10 restaurants
        
        # Update task status to analyzing
        tasks[task_id].state = "ANALYZING"
        
        # Step 3: Detailed Analysis for Top Restaurants
        # Remove logging statement
        
        # Create a list to store analysis tasks
        analysis_tasks = []
        
        # Start detailed analysis for each restaurant in parallel
        for restaurant in top_restaurants:
            # Create an analysis task for each restaurant
            task = asyncio.create_task(analyze_restaurant_for_dish_detailed(restaurant, search_request.dish))
            analysis_tasks.append(task)
        
        # Wait for all analysis tasks to complete
        analyzed_restaurants = await asyncio.gather(*analysis_tasks)
        
        # Ensure all restaurants have an ai_score
        for restaurant in analyzed_restaurants:
            if "ai_score" not in restaurant or restaurant["ai_score"] is None:
                restaurant["ai_score"] = 0.0
        
        # Sort restaurants by AI recommendation score (highest first)
        analyzed_restaurants.sort(key=lambda x: x["ai_score"], reverse=True)
        
        # Take top 5 restaurants for final result
        final_restaurants = analyzed_restaurants[:5] if len(analyzed_restaurants) >= 5 else analyzed_restaurants
        
        # Remove logging of final top 5 restaurants
        
        # Store the final result
        result = {
            "success": True,
            "dish": search_request.dish,
            "location": search_request.location,
            "restaurants": final_restaurants
        }
        
        tasks[task_id].state = "COMPLETED"
        tasks[task_id].result = result

    except Exception as e:
        # Keep error logging for debugging purposes
        print(f"Error in process_dish_search: {str(e)}")
        tasks[task_id].state = "FAILED"
        tasks[task_id].result = {"error": str(e)}

@app.post("/api/find-restaurants")
async def find_restaurants(search_request: DishSearchRequest):
    try:
        # Generate a unique task ID
        task_id = str(uuid.uuid4())
        
        # Initialize task status
        tasks[task_id] = TaskStatus(state="INITIALIZED")
        
        # Start processing in the background
        asyncio.create_task(process_dish_search(task_id, search_request))
        
        return {"task_id": task_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

