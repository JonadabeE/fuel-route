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

# Caminho para o arquivo Excel
FUEL_XLSX_FILE = os.path.join(os.path.dirname(__file__), "fuel_prices.xlsx")

# Substituímos a Google API pelo OSRM (OpenStreetMap Routing Machine)
OSRM_API_URL = "http://router.project-osrm.org/route/v1/driving"

# Função para carregar as informações dos postos de gasolina a partir do arquivo XLSX
def load_fuel_prices():
    """
    Carrega os dados de postos de combustível a partir de um arquivo Excel,
    retornando uma lista de dicionários com informações dos postos.
    """
    fuel_stations = []
    df = pd.read_excel(FUEL_XLSX_FILE)
    df = df.dropna(subset=["Latitude", "Longitude"])  # Remove entradas sem coordenadas

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

# Função para calcular a distância entre duas coordenadas usando a fórmula de Haversine
def calculate_distance(coord1, coord2):
    """
    Calcula a distância geodésica entre dois pontos (latitude, longitude).
    """
    coord1 = (float(coord1[0]), float(coord1[1]))  # [longitude, latitude] -> (latitude, longitude)
    coord2 = (float(coord2[0]), float(coord2[1]))

    distance = geodesic(coord1, coord2).miles
    return distance

# Função para validar coordenadas
def validate_coordinates(coordinate):
    """
    Valida e converte as coordenadas fornecidas para o formato float.
    Retorna as coordenadas ou None se inválidas.
    """
    try:
        lat, lon = map(float, coordinate)
        return lat, lon
    except (ValueError, TypeError):
        return None  # Retorna None se as coordenadas não forem válidas

# Função para calcular a rota usando o OSRM
def get_route(start_coords, end_coords):
    """
    Consulta a API OSRM para obter a rota entre as coordenadas de início e fim.
    Retorna a rota em formato de coordenadas ou None em caso de erro.
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
    Calcula a distância total percorrida na rota, considerando os postos de combustível.
    A rota é uma lista de coordenadas (latitude, longitude).
    """
    total_distance = 0
    
    if len(route) < 2:
        return 0

    for i in range(len(route) - 1):
        start = route[i]
        end = route[i + 1]

        start_inverted = (start[1], start[0])  # Invertendo latitude e longitude
        end_inverted = (end[1], end[0])  # Invertendo latitude e longitude

        distance = calculate_distance(start_inverted, end_inverted)  # Reutiliza a função de Haversine
        total_distance += distance
    
    if total_distance == 0:
        return 0

    return total_distance

def calculate_fuel_cost(route, affordable_stations, max_range, mpg, fuel_price):
    """
    Calcula o custo de combustível para a rota, considerando postos de combustível viáveis.
    Retorna o custo total e mensagens relacionadas aos custos de abastecimento.
    """
    total_cost = 0
    best_station = None
    best_cost = float('inf')

    # Calcular a distância total da rota
    total_distance = calculate_total_route_distance(route)

    # Calcular o custo de combustível para cada posto
    for station in affordable_stations:
        station_distance = calculate_distance((route[0][1], route[0][0]), (station['latitude'], station['longitude']))

        if station_distance <= max_range:  # O posto deve estar dentro da autonomia do veículo
            gallons_needed = total_distance / mpg  # Calcula o número de galões para percorrer a distância

            cost_at_station = gallons_needed * station['retail_price']

            # Verificar se o posto tem o custo mais baixo
            if cost_at_station < best_cost:
                best_cost = cost_at_station
                best_station = station

    if best_station is None:
        fuel_cost_messages = ["Nenhum posto dentro da autonomia do veículo."]
    else:
        fuel_cost_messages = [f"Custo de abastecimento no posto {best_station['name']} - ${best_cost:.2f}"]
    
    return best_cost, fuel_cost_messages

# Função para verificar se o posto está dentro de uma faixa geográfica relevante
def is_within_distance(post, start_coords, end_coords, max_distance=300):
    """
    Verifica se um posto está dentro de um raio máximo de 10 milhas de qualquer ponto da rota.
    """
    distance_to_start = calculate_distance((post["latitude"], post["longitude"]), start_coords)
    distance_to_end = calculate_distance((post["latitude"], post["longitude"]), end_coords)

    return distance_to_start <= max_distance or distance_to_end <= max_distance

# Função para criar um mapa interativo com a rota e postos de gasolina
def create_route_map(start_coords, finish_coords, route, fuel_stops):
    """
    Cria um mapa interativo usando a biblioteca Folium, com a rota e postos de combustível.
    """
    mid_lat = (start_coords[0] + finish_coords[0]) / 2
    mid_lon = (start_coords[1] + finish_coords[1]) / 2
    route_map = folium.Map(location=[mid_lat, mid_lon], zoom_start=12)

    route_line = folium.PolyLine(locations=[(lat, lon) for lon, lat in route], color='blue', weight=5, opacity=0.7)
    route_map.add_child(route_line)

    marker_cluster = MarkerCluster().add_to(route_map)
    for station in fuel_stops:
        folium.Marker(
            location=[station["latitude"], station["longitude"]],
            popup=f"{station['name']}<br>{station['address']}<br>Price: ${station['retail_price']}",
            icon=folium.Icon(color='green', icon='cloud')
        ).add_to(marker_cluster)

    folium.Marker(location=[start_coords[0], start_coords[1]], popup='Start', icon=folium.Icon(color='red')).add_to(route_map)
    folium.Marker(location=[finish_coords[0], finish_coords[1]], popup='Finish', icon=folium.Icon(color='blue')).add_to(route_map)

    return route_map

# Função principal para calcular a rota e identificar postos de gasolina viáveis
@api_view(["POST"])
def calculate_route(request):
    """
    Função principal que recebe as coordenadas de início e fim, calcula a rota, verifica postos de combustível
    acessíveis ao longo do caminho e retorna informações detalhadas, incluindo um mapa da rota.
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

    # Obter a rota usando o OSRM
    route = get_route(start_coords, finish_coords)
    if not route:
        return JsonResponse({"error": "Failed to retrieve route from OSRM."}, status=500)

    # Carregar postos de gasolina
    fuel_stations = load_fuel_prices()

    # Filtrar postos dentro de um raio de 10 milhas de qualquer ponto da rota
    affordable_stations = [station for station in fuel_stations if is_within_distance(station, start_coords, finish_coords)]

    # Calcular o custo total de combustível e obter as mensagens
    total_cost, fuel_cost_messages = calculate_fuel_cost(route, affordable_stations, max_range=500, mpg=10, fuel_price=3.0)

    # Criar o mapa com a rota e os postos
    route_map = create_route_map(start_coords, finish_coords, route, affordable_stations)

    # Gerar um nome único para o arquivo com base no timestamp
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    map_filename = f"route_map_{timestamp}.html"
    map_file_path = os.path.join(settings.MEDIA_ROOT, map_filename)

    # Salve o mapa com o nome único
    route_map.save(map_file_path)

    # Retorne o link do arquivo gerado
    map_url = os.path.join(settings.MEDIA_URL, map_filename)
    
    # Retornar a resposta com o link para o mapa e os postos de combustível
    response_data = {
        "map_url": map_url,
        "fuel_stops": affordable_stations,
        "total_cost": f"${total_cost:.2f}",
        "fuel_cost_messages": fuel_cost_messages
    }

    return JsonResponse(response_data)
