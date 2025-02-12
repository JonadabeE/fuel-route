import os
import requests
import pandas as pd
from django.http import JsonResponse
from rest_framework.decorators import api_view
from geopy.distance import geodesic
import folium
from folium.plugins import MarkerCluster
from django.conf import settings
import time

# Path to the Excel file containing fuel prices
FUEL_XLSX_FILE = os.path.join(os.path.dirname(__file__), "fuel_prices.xlsx")

# Replaced Google API with OSRM (OpenStreetMap Routing Machine)
OSRM_API_URL = "http://router.project-osrm.org/route/v1/driving"

def load_fuel_prices():
    """
    Loads fuel station data from an Excel file and returns a list of dictionaries
    containing station details such as name, address, city, state, and retail price.
    """
    fuel_stations = []
    df = pd.read_excel(FUEL_XLSX_FILE)
    df = df.dropna(subset=["Latitude", "Longitude"])  # Removes entries without coordinates

    for _, row in df.iterrows():
        fuel_stations.append({
            "name": row["Truckstop Name"],
            "address": row["Address"],
            "city": row["City"],
            "state": row["State"],
            "retail_price": row["Retail Price"],
            "latitude": row["Latitude"],
            "longitude": row["Longitude"]
        })

    return fuel_stations

def calculate_distance(coord1, coord2):
    """
    Calculates the geodesic distance between two points (latitude, longitude).
    """
    coord1 = (float(coord1[0]), float(coord1[1]))  # Convert to (latitude, longitude)
    coord2 = (float(coord2[0]), float(coord2[1]))

    return geodesic(coord1, coord2).miles

def validate_coordinates(coordinate):
    """
    Validates and converts the provided coordinates to floats.
    Returns the coordinates or None if invalid.
    """
    try:
        lat, lon = map(float, coordinate)
        return lat, lon
    except (ValueError, TypeError):
        return None  # Returns None if coordinates are invalid

def get_route(start_coords, end_coords):
    """
    Fetches the route from the OSRM API given start and end coordinates.
    Returns the route as a list of coordinates or None if an error occurs.
    """
    url = f"{OSRM_API_URL}/{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}?overview=full&geometries=geojson"
    response = requests.get(url)
    
    if response.status_code != 200:
        return None

    route_data = response.json()
    
    if "routes" in route_data and route_data["routes"]:
        return route_data["routes"][0]["geometry"]["coordinates"]
    
    return None

def calculate_total_route_distance(route):
    """
    Calculates the total distance of the route considering fuel stations along the way.
    The route is a list of coordinates (latitude, longitude).
    """
    total_distance = 0
    
    if len(route) < 2:
        return 0

    for i in range(len(route) - 1):
        start = route[i]
        end = route[i + 1]

        start_inverted = (start[1], start[0])  # Invert latitude and longitude
        end_inverted = (end[1], end[0])  # Invert latitude and longitude

        distance = calculate_distance(start_inverted, end_inverted)  # Reuse Haversine function
        total_distance += distance
    
    return total_distance

def calculate_fuel_cost(route, affordable_stations, max_range, mpg, fuel_price):
    """
    Calculates the fuel cost for the route considering viable fuel stations.
    Returns the total cost and messages related to fueling costs.
    """
    total_cost = 0
    best_station = None
    best_cost = float('inf')

    # Calculate the total route distance
    total_distance = calculate_total_route_distance(route)

    # Calculate fuel cost at each station
    for station in affordable_stations:
        station_distance = calculate_distance((route[0][1], route[0][0]), (station['latitude'], station['longitude']))

        if station_distance <= max_range:  # The station must be within the vehicle's range
            gallons_needed = total_distance / mpg  # Calculate gallons needed for the total distance

            cost_at_station = gallons_needed * station['retail_price']

            # Check if the station has the lowest cost
            if cost_at_station < best_cost:
                best_cost = cost_at_station
                best_station = station

    if best_station is None:
        fuel_cost_messages = ["No stations within the vehicle's range."]
    else:
        fuel_cost_messages = [f"Fuel cost at {best_station['name']} station - ${best_cost:.2f}"]
    
    return best_cost, fuel_cost_messages

def is_within_distance(post, start_coords, end_coords, max_distance=300):
    """
    Checks if a fuel station is within a certain distance from any point on the route.
    Defaults to a maximum of 300 miles from either the start or end.
    """
    distance_to_start = calculate_distance((post["latitude"], post["longitude"]), start_coords)
    distance_to_end = calculate_distance((post["latitude"], post["longitude"]), end_coords)

    return distance_to_start <= max_distance or distance_to_end <= max_distance

def create_route_map(start_coords, finish_coords, route, fuel_stops):
    """
    Creates an interactive map using the Folium library, displaying the route and fuel stations.
    """
    mid_lat = (start_coords[0] + finish_coords[0]) / 2
    mid_lon = (start_coords[1] + finish_coords[1]) / 2
    route_map = folium.Map(location=[mid_lat, mid_lon], zoom_start=12)

    # Draw the route line on the map
    route_line = folium.PolyLine(locations=[(lat, lon) for lon, lat in route], color='blue', weight=5, opacity=0.7)
    route_map.add_child(route_line)

    # Add fuel station markers to the map
    marker_cluster = MarkerCluster().add_to(route_map)
    for station in fuel_stops:
        folium.Marker(
            location=[station["latitude"], station["longitude"]],
            popup=f"{station['name']}<br>{station['address']}<br>Price: ${station['retail_price']}",
            icon=folium.Icon(color='green', icon='cloud')
        ).add_to(marker_cluster)

    # Add markers for the start and finish points
    folium.Marker(location=[start_coords[0], start_coords[1]], popup='Start', icon=folium.Icon(color='red')).add_to(route_map)
    folium.Marker(location=[finish_coords[0], finish_coords[1]], popup='Finish', icon=folium.Icon(color='blue')).add_to(route_map)

    return route_map

@api_view(["POST"])
def calculate_route(request):
    """
    Main function that receives start and finish coordinates, calculates the route, checks for fuel stations
    accessible along the way, and returns detailed information, including a map of the route.
    """
    data = request.data
    start_location = data.get("start_location")
    finish_location = data.get("finish_location")

    if not start_location or not finish_location:
        return JsonResponse({"error": "Both start_location and finish_location fields are required."}, status=400)

    try:
        start_coords = validate_coordinates(start_location.split(","))
        finish_coords = validate_coordinates(finish_location.split(","))
        if not start_coords or not finish_coords:
            raise ValueError("Invalid coordinates")
    except ValueError:
        return JsonResponse({"error": "Invalid coordinates format. Expected 'lat,lon'."}, status=400)

    # Fetch the route using OSRM
    route = get_route(start_coords, finish_coords)
    if not route:
        return JsonResponse({"error": "Failed to retrieve route from OSRM."}, status=500)

    # Load fuel station data
    fuel_stations = load_fuel_prices()

    # Filter stations within 10 miles of any point on the route
    affordable_stations = [station for station in fuel_stations if is_within_distance(station, start_coords, finish_coords)]

    # Calculate total fuel cost and generate cost messages
    total_cost, fuel_cost_messages = calculate_fuel_cost(route, affordable_stations, max_range=500, mpg=10, fuel_price=3.0)

    # Create map with the route and fuel stations
    route_map = create_route_map(start_coords, finish_coords, route, affordable_stations)

    # Generate a unique file name based on the timestamp
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    map_filename = f"route_map_{timestamp}.html"
    map_file_path = os.path.join(settings.MEDIA_ROOT, map_filename)

    # Save the map to the file system
    route_map.save(map_file_path)

    # Return the map file URL and other data
    map_url = os.path.join(settings.MEDIA_URL, map_filename)
    
    response_data = {
        "map_url": map_url,
        "fuel_stops": affordable_stations,
        "total_cost": f"${total_cost:.2f}",
        "fuel_cost_messages": fuel_cost_messages
    }

    return JsonResponse(response_data)
