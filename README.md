# Fuel Route Optimization API

## Description

This project provides an API to calculate the optimal route between two locations within the USA, while suggesting fuel stations along the way based on fuel prices. It assumes a vehicle with a maximum range of 500 miles and calculates the total cost of fuel, considering a fuel efficiency of 10 miles per gallon. The API returns a map of the route, along with details of the best fuel stops and the total fuel cost.

### Features:
- Calculate the optimal driving route between a start and finish location using a free routing API (OSRM - OpenStreetMap Routing Machine).
- Display fuel stations within a reasonable distance from the route.
- Calculate the total fuel cost based on fuel price and the vehicle's fuel efficiency (10 mpg).
- Return an interactive map with the route and fuel stations along the way.
- Provide cost-effective fuel station suggestions based on the best prices.

## API Endpoints

### `POST /calculate_route/`
This endpoint calculates the optimal route between the start and finish locations, returns fuel stations within a relevant distance, and computes the total cost of fuel. It also generates a route map.

#### Request Body

```json
{
  "start_location": "latitude,longitude",  // Start location coordinates
  "finish_location": "latitude,longitude"  // Finish location coordinates
}

{
  "map_url": "path/to/generated/map.html",  // URL of the generated route map
  "fuel_stops": [  // List of fuel stations along the route
    {
      "name": "Station Name",
      "address": "Station Address",
      "city": "City",
      "state": "State",
      "retail_price": 3.49,
      "latitude": 38.8977,
      "longitude": -77.0365
    },
    ...
  ],
  "total_cost": "$50.35",  // Total fuel cost for the trip
  "fuel_cost_messages": ["Refuel at Station XYZ - $50.35"]  // Messages about fuel cost
}
```
## Error Responses

- **400 Bad Request**: Missing or invalid coordinates.
- **500 Internal Server Error**: Unable to retrieve route or other internal errors.

## Setup

### Prerequisites

- Python 3.8+
- Django
- Django Rest Framework
- Geopy
- Folium
- Pandas
- Requests

### Usage

To use the API, send a `POST` request to the `/calculate_route/` endpoint with the start and finish locations in the correct format (latitude, longitude). The API will return a JSON response containing a link to the generated route map, fuel stations along the route, and the total fuel cost.

## Dependencies

- **OSRM API**: Used for calculating the route between the start and finish locations.
- **Geopy**: For calculating distances between coordinates using the Haversine formula.
- **Folium**: For generating interactive maps.
- **Pandas**: For loading and processing the fuel prices data from an Excel file.
