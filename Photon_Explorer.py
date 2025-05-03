import pandas as pd
import numpy as np
import plotly.graph_objs as go
import pyarrow.feather as feather
from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import dash_leaflet as dl
from flask_caching import Cache

# Initialize app with caching
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
cache = Cache(app.server, config={"CACHE_TYPE": "SimpleCache"})
TIMEOUT = 600  # seconds

regions = [
    "Smadalen_Jotunheimen", "Heimdalshoe_Jotunheimen",
    "Musvoldalen_Rondane", "StorSvuku_Femundsmarka"
]
region_options = [{'label': region, 'value': region} for region in regions]

@cache.memoize(timeout=TIMEOUT)
def load_data(region):
    with open(f'Data/{region}_ATL08.feather', 'rb') as f:
        atl08 = feather.read_feather(f)
    with open(f'Data/{region}_ATL03SR.feather', 'rb') as f:
        atl03 = feather.read_feather(f)
    return atl08, atl03

class_colors = {
    "ATL08": "#7b3294",
    "Noise": "gray",
    "Unclassified": "gray",
    "Canopy": "green",
    "Canopy Top": "lime",
    "Ground": "brown"
}

app.layout = html.Div([
    html.H3("Photon Explorer", style={'marginBottom': '5px'}),

    html.Div([
        html.Div(dcc.Dropdown(id='region-dropdown', options=region_options, value='Smadalen_Jotunheimen'), style={'width': '33%', 'marginRight': '8px'}),
        html.Div(dcc.Dropdown(id='date-dropdown'), style={'width': '33%', 'marginRight': '8px'}),
        html.Div(dcc.Dropdown(id='pb-dropdown'), style={'width': '33%'})
    ], style={'display': 'flex', 'marginBottom': '5px'}),

    html.Div(id='plot-title', style={'fontWeight': 'bold', 'fontSize': '18px', 'marginBottom': '8px'}),

    html.Div([
        html.Label("Photon Classes", style={'fontWeight': 'bold', 'marginRight': '15px'}),
        dcc.Checklist(
            id='class-checklist',
            options=[{
                'label': html.Span([
                    html.Span(style={
                        'display': 'inline-block', 'width': '12px', 'height': '12px',
                        'backgroundColor': class_colors[label], 'borderRadius': '50%',
                        'marginRight': '6px'
                    }),
                    html.Span(label)
                ], style={'display': 'inline-flex', 'alignItems': 'center'}),
                'value': label
            } for label in class_colors.keys()],
            value=list(class_colors.keys()),
            labelStyle={'display': 'inline-flex', 'alignItems': 'center', 'marginRight': '20px'},
            inputStyle={'marginRight': '6px'}
        )
    ], style={
        'backgroundColor': '#f9f9f9',
        'padding': '10px 10px 5px 10px',
        'marginBottom': '8px',
        'borderRadius': '8px',
        'border': '1px solid #ccc',
        'display': 'flex',
        'flexWrap': 'wrap',
        'alignItems': 'center'
    }),

    dcc.Loading(
        type="circle",
        children=dcc.Graph(id='photon-plot', config={'staticPlot': False})
    ),

    html.H4("Map View (Norge i bilder WMS)", style={'marginTop': '20px'}),
    dl.Map(center=[61.72, 8.75], zoom=13, children=[
        dl.WMSTileLayer(
            url="https://wms.geonorge.no/skwms1/wms.nib?",
            layers="Nibcache", format="image/png", transparent=True,
            attribution="© Norge i bilder / Geonorge", version="1.1.1"
        ),
        dl.Marker(id='photon-marker', position=[61.72, 8.75], autoPan=True)
    ], id='map', style={'height': '600px', 'width': '100%', 'marginTop': '10px'})
])

@app.callback(
    Output('date-dropdown', 'options'),
    Output('date-dropdown', 'value'),
    Input('region-dropdown', 'value')
)
def update_date_options(region):
    df, _ = load_data(region)
    options = [{'label': str(val), 'value': val} for val in sorted(df['date'].unique())]
    return options, options[0]['value'] if options else None

@app.callback(
    Output('pb-dropdown', 'options'),
    Output('pb-dropdown', 'value'),
    Input('region-dropdown', 'value'),
    Input('date-dropdown', 'value')
)
def update_pb_options(region, date):
    df, _ = load_data(region)
    if date:
        df = df[df['date'] == date]
        options = [{'label': str(val), 'value': val} for val in sorted(df['pb'].unique())]
        return options, options[0]['value'] if options else None
    return [], None

@app.callback(
    Output('photon-plot', 'figure'),
    Output('photon-marker', 'position'),
    Output('map', 'center'),
    Output('plot-title', 'children'),
    Input('region-dropdown', 'value'),
    Input('date-dropdown', 'value'),
    Input('pb-dropdown', 'value'),
    Input('photon-plot', 'clickData'),
    Input('class-checklist', 'value')
)
def update_plot(region, date, pb, photon_click, visible_classes):
    df, atl03 = load_data(region)

    df_select = df[(df.date == date) & (df.pb == pb)]
    df_select = df_select[df_select['h_max_canopy'] > -999]
    atl03_select = atl03[(atl03.date == date) & (atl03.pb == pb)]

    # Find min/max for h_max_canopy
    hmin, hmax = df_select['h_max_canopy'].min(), df_select['h_max_canopy'].max()
    max_row = df_select.loc[df_select['h_max_canopy'].idxmax()]
    min_row = df_select.loc[df_select['h_max_canopy'].idxmin()]
    print(f"MAX h_max_canopy: {max_row['h_max_canopy']} at (Lat: {max_row['latitude']}, Lon: {max_row['longitude']})")
    print(f"MIN h_max_canopy: {min_row['h_max_canopy']} at (Lat: {min_row['latitude']}, Lon: {min_row['longitude']})")

    clicked_lat = clicked_lon = clicked_height = None
    if photon_click and 'points' in photon_click:
        point = photon_click['points'][0]
        clicked_lat = point.get('x')
        clicked_height = point.get('y')
        if 'customdata' in point and point['customdata']:
            clicked_lon = point['customdata'][0]

    fig = go.Figure()

    if "ATL08" in visible_classes:
        fig.add_trace(go.Scattergl(
            x=df_select['latitude'],
            y=df_select['h_te_median'],
            mode='markers',
            name='ATL08',
            customdata=[[val] for val in df_select['longitude']],
            marker=dict(
                size=np.sqrt(df_select['n_te_photons']) * 2,
                color=df_select['h_max_canopy'],
                cmin=hmin,
                cmax=hmax,
                colorscale='Purples',
                showscale=True,
                colorbar=dict(
                    title=dict(text='h_max_canopy', side='right'),
                    len=1.0,
                    y=0.5,
                    yanchor='middle',
                    thickness=15
                ),
                line=dict(width=0.2, color='DarkSlateGrey')
            ),
            hovertemplate='Lat: %{x:.5f}<br>Lon: %{customdata[0]:.5f}<br>h_te_median: %{y:.2f} m'
        ))

    class_map = {0: "Noise", 4: "Unclassified", 2: "Canopy", 3: "Canopy Top", 1: "Ground"}
    for class_val, label in class_map.items():
        if label in visible_classes:
            subset = atl03_select[atl03_select['atl08_class'] == class_val]
            fig.add_trace(go.Scattergl(
                x=subset['lat_ph'],
                y=subset['height'],
                mode='markers',
                name=label,
                marker=dict(color=class_colors[label], size=3),
                customdata=[[val] for val in subset['lon_ph']],
                hovertemplate='Lat: %{x:.5f}<br>Lon: %{customdata[0]:.5f}<br>Height: %{y:.2f} m'
            ))

    if clicked_lat and clicked_lon and clicked_height:
        fig.add_trace(go.Scattergl(
            x=[clicked_lat],
            y=[clicked_height],
            mode='markers',
            marker=dict(color='red', size=10, symbol='x'),
            name='Selected',
            showlegend=False
        ))
  # ✅ Add treeline
    fig.add_shape(
        type='line',
        x0=df_select['latitude'].min(),
        x1=df_select['latitude'].max(),
        y0=1300,
        y1=1300,
        line=dict(color='green', width=2, dash='dash'),
    )
    fig.update_layout(
        xaxis_title='Latitude',
        yaxis_title='h_te_median (m)',
        height=700,
        uirevision='static',
        showlegend=False
    )

    title = f"ATL03 + ATL08 | {region} | Date: {date} | PB: {pb}"
    return fig, [clicked_lat, clicked_lon] if clicked_lat and clicked_lon else [61.72, 8.75], [clicked_lat, clicked_lon] if clicked_lat and clicked_lon else [61.72, 8.75], title

if __name__ == '__main__':
    app.run(debug=True, port=8050)
