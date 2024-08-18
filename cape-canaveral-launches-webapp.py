import requests
import json
from datetime import datetime, timedelta
import pandas as pd
import folium
from folium.plugins import MarkerCluster
from flask import Flask, render_template_string
import threading
import time

app = Flask(__name__)

# Global variable to store the latest map
latest_map = None
last_update_time = datetime.now()

def fetch_upcoming_launches():
    url = "https://ll.thespacedevs.com/2.2.0/launch/upcoming/?format=json&location__ids=12"
    try:
        response = requests.get(url)
        response.raise_for_status()
        launch_data = response.json()
        return launch_data
    except requests.RequestException as e:
        print(f"Error fetching launch data: {e}")
        return None

def process_launch_data(data):
    now = datetime.utcnow()
    one_month_later = now + timedelta(days=30)
    
    processed_data = []
    
    for launch in data['results']:
        launch_time = datetime.strptime(launch['net'], "%Y-%m-%dT%H:%M:%SZ")
        
        if launch_time <= one_month_later:
            processed_data.append({
                'T-0': launch['net'],
                'Mission': launch['mission']['name'] if launch['mission'] else "N/A",
                'Pad Latitude': launch['pad']['latitude'],
                'Pad Longitude': launch['pad']['longitude'],
                'Pad': launch['pad']['name'],
                'Location': launch['pad']['location']['name']
            })
    
    return pd.DataFrame(processed_data)

def calculate_countdown(t0):
    launch_time = datetime.strptime(t0, "%Y-%m-%dT%H:%M:%SZ")
    now = datetime.utcnow()
    time_difference = launch_time - now
    return str(time_difference).split('.')[0]  # Remove microseconds

def create_map(df):
    # Create a map centered on Cape Canaveral
    m = folium.Map(location=[28.4555, -80.5287], zoom_start=10)
    
    # Create a MarkerCluster
    marker_cluster = MarkerCluster().add_to(m)
    
    # Add markers for each launch
    for _, launch in df.iterrows():
        popup_text = f"Mission: {launch['Mission']}<br>Pad: {launch['Pad']}<br>Countdown: {calculate_countdown(launch['T-0'])}"
        
        folium.Marker(
            location=[launch['Pad Latitude'], launch['Pad Longitude']],
            popup=popup_text,
            icon=folium.Icon(color='red', icon='rocket', prefix='fa')
        ).add_to(marker_cluster)
    
    return m

def update_data():
    global latest_map
    while True:
        launch_data = fetch_upcoming_launches()
        if launch_data:
            df = process_launch_data(launch_data)
            df = df.sort_values('T-0').head(8)  # Sort by launch date and get the next 4 launches
            latest_map = create_map(df)
            last_update_time = datetime.now()
        time.sleep(300)  # Wait for 5 minutes

@app.route('/')
def home():
    global latest_map
    if latest_map is None:
        return "Loading data... Please refresh in a moment."
    
    map_html = latest_map.get_root().render()
    
    update_time = last_update_time.strftime('%Y-%m-%d %H:%M:%S') if last_update_time else "Not available"

    page_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Cape Canaveral Launches</title>
        <meta http-equiv="refresh" content="300">
        <script>
            function updateCountdown() {{
                var elements = document.getElementsByClassName('countdown');
                for (var i = 0; i < elements.length; i++) {{
                    var launchTime = new Date(elements[i].getAttribute('data-launch-time'));
                    var now = new Date();
                    var diff = launchTime - now;
                    var days = Math.floor(diff / (1000 * 60 * 60 * 24));
                    var hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                    var minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
                    var seconds = Math.floor((diff % (1000 * 60)) / 1000);
                    elements[i].innerHTML = days + "d " + hours + "h " + minutes + "m " + seconds + "s";
                }}
            }}
            setInterval(updateCountdown, 1000);
        </script>
    </head>
    <body>
        <h1>Upcoming Cape Canaveral Launches</h1>
        <h2>as of {update_time}</h2>
        {map_html}
        <p>Data refreshes every 5 minutes. Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </body>
    </html>
    """
    
    return page_html

if __name__ == "__main__":
    # Start the data update thread
    update_thread = threading.Thread(target=update_data)
    update_thread.daemon = True
    update_thread.start()
    
    # Run the Flask app
    app.run(debug=True)
