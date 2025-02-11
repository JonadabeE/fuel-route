import pandas as pd
import os
import requests
import csv
import time
from django.http import JsonResponse
from rest_framework.decorators import api_view
import geopy.distance

# Path to the CSV file
FUEL_CSV_FILE = os.path.join(os.path.dirname(__file__), "fuel_prices.csv")

# Google API Key (Substitua pela sua chave válida)
API_KEY = "AIzaSyBogaEWk_zBktHsax4yWagruLwibpgMNbM"

# Google Geocoding API URL
GEOCODE_API_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Função para obter coordenadas a partir de um endereço
def get_coordinates(address):
    params = {
        "address": address,
        "key": API_KEY
    }
    response = requests.get(GEOCODE_API_URL, params=params)
    
    if response.status_code == 200:
        data = response.json()
        if data["status"] == "OK":
            location = data["results"][0]["geometry"]["location"]
            return float(location["lat"]), float(location["lng"])
    
    return None, None  # Retorna None se o endereço não for encontrado

# Google Directions API URL
DIRECTIONS_API_URL = "https://maps.googleapis.com/maps/api/directions/json"

@api_view(["POST"])
def calculate_route(request):
    data = request.data
    start_location = data.get("start_location")
    finish_location = data.get("finish_location")

    if not start_location or not finish_location:
        return JsonResponse({"error": "Both start_location and finish_location fields are required."}, status=400)

    # Solicita dados da rota na Google Directions API
    params = {
        "origin": start_location,
        "destination": finish_location,
        "key": API_KEY
    }
    route_response = requests.get(DIRECTIONS_API_URL, params=params)

    if route_response.status_code != 200:
        return JsonResponse({"error": "Failed to retrieve route data."}, status=500)

    route_data = route_response.json()

    if route_data["status"] != "OK" or "routes" not in route_data:
        return JsonResponse({"error": "Could not calculate the route."}, status=400)

    total_distance_miles = sum(leg["distance"]["value"] for leg in route_data["routes"][0]["legs"]) / 1609  # Convert meters to miles

    response_data = {
        "route_map": f"https://www.google.com/maps/dir/{start_location}/{finish_location}",
        "total_distance_miles": round(total_distance_miles, 2),
    }

    return JsonResponse(response_data)


def update_csv_with_coordinates():
    # Carregar o CSV com delimitador adequado e garantindo que as aspas sejam tratadas corretamente
    df = pd.read_csv(FUEL_CSV_FILE, sep=",", quotechar='"', encoding='utf-8')  # Ajuste para vírgula e aspas

    # Limpeza de possíveis espaços extras nos nomes das colunas
    df.columns = df.columns.str.strip()

    # Adiciona as colunas de Latitude e Longitude, se não existirem
    if 'Latitude' not in df.columns or 'Longitude' not in df.columns:
        df['Latitude'] = None
        df['Longitude'] = None

    needs_update = False  # Flag para verificar se alguma atualização foi feita

    # Iterar sobre as linhas do DataFrame
    for index, row in df.iterrows():
        # Verifica se as colunas de endereço, cidade, estado e nome do truckstop têm dados
        if pd.notna(row['Address']) and pd.notna(row['City']) and pd.notna(row['State']) and pd.notna(row['Truckstop Name']):
            address = f"{row['Address']}, {row['City']}, {row['State']}"

            # Verifica se a latitude e longitude estão ausentes ou vazias
            if pd.isna(row['Latitude']) or pd.isna(row['Longitude']):
                lat, lon = get_coordinates(address)

                if lat and lon:
                    df.at[index, 'Latitude'] = lat
                    df.at[index, 'Longitude'] = lon
                    needs_update = True
                    print(f"Obtido lat/long para: {address} -> {lat}, {lon}")
                else:
                    print(f"Não foi possível obter lat/long para: {address}")

                time.sleep(0.5)  # Pequeno delay para evitar limite de requisições da API
        else:
            print(f"Linha ignorada por dados incompletos: {row}")

    # Se alguma atualização foi feita, salva de volta no CSV
    if needs_update:
        df.to_csv(FUEL_CSV_FILE, index=False, sep=",", encoding='utf-8')  # Salva com vírgula como delimitador

# Executa a atualização do CSV
update_csv_with_coordinates()


# This sets up the free map API configuration for route calculation
MAPS_API_URL = "https://router.project-osrm.org/route/v1/driving"

# This function loads the fuel stations' information from the CSV file
def load_fuel_prices():
    fuel_stations = []
    with open(FUEL_CSV_FILE, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            fuel_stations.append({
                "id": row["OPIS Truckstop ID"],
                "name": row["Truckstop Name"],
                "address": row["Address"],
                "city": row["City"],
                "state": row["State"],
                "retail_price": float(row["Retail Price"]),
                "latitude": float(row["Latitude"]),  # Coordinates of each station
                "longitude": float(row["Longitude"])
            })
    return fuel_stations

# This function calculates the distance between two coordinates using the Haversine formula
def calculate_distance(coord1, coord2):
    return geopy.distance.distance(coord1, coord2).miles

# This function checks if a fuel station is within a reasonable distance (10 miles) from the route
def is_within_route_range(route_coordinates, station_coords, max_distance=10):
    for i in range(len(route_coordinates) - 1):
        segment_start = route_coordinates[i]
        segment_end = route_coordinates[i + 1]
        distance_to_segment = geopy.distance.distance(station_coords, segment_start).miles + \
                              geopy.distance.distance(station_coords, segment_end).miles
        segment_distance = geopy.distance.distance(segment_start, segment_end).miles
        if distance_to_segment <= segment_distance + max_distance:
            return True
    return False

@api_view(["POST"])
def calculate_route(request):
    data = request.data
    start_location = data.get("start_location")
    finish_location = data.get("finish_location")

    if not start_location or not finish_location:
        return JsonResponse({"error": "Both start_location and finish_location fields are required."}, status=400)

    # Request route data from the API and extract the total distance and coordinates
    route_response = requests.get(f"{MAPS_API_URL}/{start_location};{finish_location}?overview=true&geometries=geojson")
    route_data = route_response.json()

    if "routes" not in route_data or not route_data["routes"]:
        return JsonResponse({"error": "Could not calculate the route."}, status=400)

    total_distance_miles = route_data["routes"][0]["distance"] / 1609  # Convert meters to miles
    route_coordinates = route_data["routes"][0]["geometry"]["coordinates"]  # Coordinates of the route

    # Vehicle parameters
    mpg = 10  # Miles per gallon
    max_range = 500  # Maximum range of the vehicle
    MIN_FUEL_RESERVE = 50  # Minimum fuel reserve in miles
    current_fuel = max_range  # The vehicle starts with a full tank
    fuel_stations = load_fuel_prices()

    remaining_distance = total_distance_miles
    current_location = start_location
    stops = []
    total_fuel_cost = 0

    # Logic for deciding when to refuel
    while remaining_distance > 0:
        autonomy_left = current_fuel * mpg  # How many miles the vehicle can go with the current fuel

        # Filter stations that are affordable and within range of the route
        affordable_stations = [
            station for station in fuel_stations if station["retail_price"] is not None and is_within_route_range(route_coordinates, (station["latitude"], station["longitude"]))
        ]

        if affordable_stations:
            cheapest_station = min(affordable_stations, key=lambda s: s["retail_price"])

            # Calculate the distance to the cheapest station
            distance_to_station = calculate_distance(current_location, (cheapest_station["latitude"], cheapest_station["longitude"]))

            # Calculate how much fuel is needed to reach that station
            fuel_needed = distance_to_station / mpg

            # Check if the station is within reach, considering the remaining fuel and minimum reserve
            if distance_to_station <= autonomy_left - MIN_FUEL_RESERVE:
                cost = fuel_needed * cheapest_station["retail_price"]

                stops.append({
                    "location": f"{cheapest_station['city']}, {cheapest_station['state']}",
                    "fuel_price": cheapest_station["retail_price"],
                    "fuel_needed": round(fuel_needed, 2),
                    "cost": round(cost, 2)
                })

                total_fuel_cost += cost
                current_fuel = max_range  # Refill the tank
                remaining_distance -= distance_to_station  # Subtract the traveled distance
            else:
                remaining_distance -= autonomy_left  # Continue with the remaining autonomy
        else:
            return JsonResponse({"error": "No fuel stations found along the route."}, status=400)

    # Check if there's still distance to cover to the destination, considering the fuel reserve
    if remaining_distance > 0:
        final_leg_fuel_needed = remaining_distance / mpg
        stops.append({
            "location": "Final Destination",
            "fuel_needed": round(final_leg_fuel_needed, 2),
            "cost": round(final_leg_fuel_needed * cheapest_station["retail_price"], 2)
        })

    response_data = {
        "route_map": f"https://www.google.com/maps/dir/{start_location}/{finish_location}",
        "fuel_stops": stops,
        "total_fuel_cost": round(total_fuel_cost, 2)
    }

    return JsonResponse(response_data)
