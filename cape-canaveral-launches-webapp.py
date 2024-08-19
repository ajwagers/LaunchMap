import requests
import json, jsonify
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
latest_data = None
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

def create_map(df):
    # Create a map centered on Cape Canaveral
    m = folium.Map(location=[28.4555, -80.5287], zoom_start=10)
    
    # Create a MarkerCluster
    marker_cluster = MarkerCluster().add_to(m)
    
    # Add markers for each launch
    for index, launch in df.iterrows():
        popup_text = f"Mission: {launch['Mission']}<br>Pad: {launch['Pad']}<br>T-0: {launch['T-0']}"
        
        if index == 0:
            folium.Marker(
                location=[launch['Pad Latitude'], launch['Pad Longitude']],
                popup=popup_text,
                icon=folium.Icon(color='green', icon='rocket', prefix='fa'),
                tooltip="Next Launch!"
            ).add_to(m)
        else:
            folium.Marker(
                location=[launch['Pad Latitude'], launch['Pad Longitude']],
                popup=popup_text,
                icon=folium.Icon(color='red', icon='rocket', prefix='fa')
            ).add_to(marker_cluster)
    
    return m

def update_data():
    global latest_map, latest_data, last_update_time
    while True:
        launch_data = fetch_upcoming_launches()
        if launch_data:
            df = process_launch_data(launch_data)
            df = df.sort_values('T-0')  # Sort by launch date and get the next 4 launches
            latest_map = create_map(df)
            latest_data = df.to_dict('records')
            last_update_time = datetime.now()
        time.sleep(300)  # Wait for 5 minutes

def load_initial_data():
    global latest_map, latest_data, last_update_time
    retries = 5
    while retries > 0:
        launch_data = fetch_upcoming_launches()
        if launch_data:
            df = process_launch_data(launch_data)
            df = df.sort_values('T-0')
            latest_map = create_map(df)
            latest_data = df.to_dict('records')
            last_update_time = datetime.now()
            print("Initial data loaded successfully")
            return True
        else:
            print(f"Failed to load initial data. Retries left: {retries}")
            retries -= 1
            time.sleep(5)
    print("Failed to load initial data after multiple attempts")
    return False

@app.route('/')
def home():
    global latest_map, latest_data, last_update_time
    if latest_map is None or latest_data is None:
        return "Error: Unable to load launch data. Please try again later."
    
    map_html = latest_map.get_root().render()
    next_launch = latest_data[0] if latest_data else None
    
    update_time = last_update_time.strftime('%Y-%m-%d %H:%M:%S') if last_update_time else "Not available"

    page_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Cape Canaveral Launches</title>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/jquery/3.6.0/jquery.min.js"></script>
        <script>
            function updateCountdown() {{
                $.getJSON('/get_next_launch', function(data) {{
                    var launchTime = new Date(data.T0);
                    var now = new Date();
                    var diff = launchTime - now;
                    var days = Math.floor(diff / (1000 * 60 * 60 * 24));
                    var hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                    var minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
                    var seconds = Math.floor((diff % (1000 * 60)) / 1000);
                    $('#next-launch-countdown').html('T-' + days + "d " + hours + "h " + minutes + "m " + seconds + "s");
                    $('#next-launch-mission').text(data.Mission);
                }}
            }}
            $(document).ready(function() {{
                updateCountdown();  // Call immediately on page load
                setInterval(updateCountdown, 1000);
            }});
            setInterval(function() {{
                $.getJSON('/get_update_time', function(data) {{
                    $('#last-update-time').text(data.update_time);
                }});
            }}, 30000);
        </script>
    </head>
    <body>
        <h1>Upcoming Cape Canaveral Launches</h1>
         <h2>Next Launch: <span id="next-launch-mission">{next_launch['Mission'] if next_launch else 'Loading...'}</span></h2>
        <h2>Countdown: <span id="next-launch-countdown">Loading...</span></h2>
        {map_html}
        <p>Data refreshes every 5 minutes. Last updated: <span id="last-update-time">{update_time}</span></p>
    </body>
    </html>
    """
    
    return page_html

@app.route('/get_next_launch')
def get_next_launch():
    global latest_data
    if latest_data:
        return jsonify({
            'Mission': latest_data[0]['Mission'],
            'T0': latest_data[0]['T-0']
        })
    return jsonify({})

@app.route('/get_update_time')
def get_update_time():
    global last_update_time
    return jsonify({
        'update_time': last_update_time.strftime('%Y-%m-%d %H:%M:%S') if last_update_time else "Not available"
    })

if __name__ == "__main__":
    # Load initial data
    if load_initial_data():
        # Start the data update thread
        update_thread = threading.Thread(target=update_data)
        update_thread.daemon = True
        update_thread.start()
    
        # Run the Flask app
        app.run(debug=True)
    else:
        print("Failed to start application due to a data loading error.")
