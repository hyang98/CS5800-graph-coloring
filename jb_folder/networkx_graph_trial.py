# Notes: requires networkx library
# works with Python ver 3.14

import argparse                     # command line options
from pathlib import Path            # builds file paths relative to this file

import networkx as nx               # networkx used for making graph
import matplotlib.pyplot as plt     # matplotlib used for plotting data in visual graphic
import matplotlib.image as mpimg    # used to show background image
import time                         # for performance benchmarking

from greedy_coloring import ALGORITHMS, NX_STRATEGY_NAMES   # our copies of 4 networkx algorithms


# data files live in read_folder/data; paths are built from this file's location
# so the script can be run from any directory
DATA_DIR = Path(__file__).resolve().parent.parent / "read_folder" / "data"
LOCATIONS_FILE = DATA_DIR / "county_locations_cleanedRL.csv"
ADJACENCY_FILE = DATA_DIR / "county_adjacency_cleanedRL.txt"


def import_data(verbose=False) -> tuple[dict, list]:
    """imports two files, returns a tuple: dict of locations, list of adjacencies"""

    # in order to filter counties to the continental US, the following min / max values are used
    # original data file includes AK, HI, PR, Guam, American Samoa, etc that should be ignored
    # This essentially creates a box around the continental US
    MIN_LONG = -125     # western edge
    MAX_LONG = -65      # eastern edge
    MIN_LAT = 24        # southern edge
    MAX_LAT = 50        # northern edge


    # Import county names and location data (lat and long) from file ------------------------------
    # This represents Nodes on a graph
    county_locations = {}
    with open(LOCATIONS_FILE, 'r') as county_loc_file:
        co_loc_header = next(county_loc_file)       # skips first line

        line_number = 0
        for line in county_loc_file:
            fips_code, name, longitude, latitude = line.strip().split(",")

            # filters out counties outside of continental US
            if MIN_LONG < float(longitude) < MAX_LONG and MIN_LAT < float(latitude) < MAX_LAT:
                county_locations[fips_code] = {
                    "fips_code": fips_code,
                    "county_name": name,
                    "longitude": longitude,
                    "latitude": latitude
                }
            line_number += 1

    if verbose:
        print(f"location file rows read: {line_number}, kept (continental US): {len(county_locations)}")


    # Import county adjacency (neighbor borders) data from file, add lat and long info ------------
    # This represents Edges on a graph
    county_adj_data = []
    with open(ADJACENCY_FILE, "r") as county_adj_file:
        co_adj_header = next(county_adj_file)       # skips first line

        line_number = 0
        key_errors = 0
        for line in county_adj_file:
            county_name, county_geoid, neighbor_name, neighbor_geoid, border_length = line.strip().split("|")

            county_lat = "25"       # these are sentinel values to show when the data is not present
            county_long = "-66"     # sentinel value
            # There could be GEOIDs missing from the location data file
            # If not there, this avoids error
            try:
                county_lat = county_locations[county_geoid]["latitude"]
                county_long = county_locations[county_geoid]["longitude"]
            except KeyError as e:
                # KeyError occurs when a Geoid (FIPS code) is in the Adj file but not in the location file
                key_errors += 1
            else:
                # this runs only if the try block succeeds
                county_adj_data.append({
                    "co_name":  county_name,
                    "co_geoid": county_geoid,
                    "co_lat":   county_lat,
                    "co_long":  county_long,
                    "neighbor_name": neighbor_name,
                    "neighbor_geoid": neighbor_geoid,
                    "border_length": border_length
                })
            line_number += 1

    if verbose:
        print("Number of KeyErrors: ", key_errors)
        print(f"Adjacency file rows read: {line_number}, kept: {len(county_adj_data)}")

        # prints five example lines for each data set
        print("Example of County Locations: ")
        for key, value in list(county_locations.items())[:5]:
            print(key, value)
        # Example data:
        # 01059 {'fips_code': '01059', 'county_name': 'Franklin', 'longitude': '-87.843283', 'latitude': '34.44238135'}

        print("Example County Adjacency Data: ")
        for i in range(5):
            print(county_adj_data[i])
        # Example data:
        # {'co_name': 'Autauga County, AL', 'co_geoid': '01001', 'co_lat': '32.53514228', 'co_long': '-86.64289976',
        #           'neighbor_name': 'Chilton County, AL', 'neighbor_geoid': '01021', 'border_length': '52284'}

    return county_locations, county_adj_data


def build_graph(county_locations, county_adj_data):
    """returns a tuple: the graph, and a dict of node positions (long, lat)"""
    # create empty graph
    G = nx.Graph()

    # Create graph nodes (each county) and node positions (lat & long) --------
    positions = {}
    for co_geoid, county in county_locations.items():
        G.add_node(co_geoid)
        lat = float(county['latitude'])
        long = float(county['longitude'])
        positions[co_geoid] = (long, lat)


    # Creating graph edges based on borders in adjacency data -----------------
    for border in county_adj_data:
        edge_start = border['co_geoid']
        edge_end = border['neighbor_geoid']
        G.add_edge(edge_start, edge_end)

    return G, positions


def load_county_graph(verbose=False):
    """imports the data files and builds the county graph, returns (G, positions)"""
    county_locations, county_adj_data = import_data(verbose)
    return build_graph(county_locations, county_adj_data)


def color_graph(G, strategy="dsatur", impl="networkx") -> dict:
    """returns a dict that maps each node to a color number (0, 1, 2, ...)

    impl="networkx" uses networkx's greedy_color. impl="local" uses our copies in
    greedy_coloring/, which only know: welsh_powell, dsatur, smallest_last, independent_set
    """
    if impl == "local":
        return ALGORITHMS[strategy](G)
    if impl != "networkx":
        raise ValueError(f"impl must be 'networkx' or 'local', not {impl!r}")

    # our four names are translated to the networkx strategy names below,
    # any other networkx strategy string is passed through unchanged
    strategy = NX_STRATEGY_NAMES.get(strategy, strategy)

    # these are the built-in greedy coloring strategies.  Will also accept a custom function
    # https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.coloring.greedy_color.html
    """
    'largest_first'
    'random_sequential'
    'smallest_last'
    'independent_set'
    'connected_sequential_bfs'
    'connected_sequential_dfs'
    'connected_sequential' # (alias for the previous strategy)
    'saturation_largest_first'
    'DSATUR' # (alias for the previous strategy)
    """
    return nx.coloring.greedy_color(G, strategy=strategy, interchange=False)


def num_colors(coloring) -> int:
    """number of colors used (color numbers start at 0)"""
    return max(coloring.values()) + 1 if coloring else 0


def validate_coloring(G, coloring) -> bool:
    """True if every node has a color and no edge connects two nodes of the same color"""
    if any(node not in coloring for node in G.nodes()):
        return False
    return all(coloring[u] != coloring[v] for u, v in G.edges())


def graph_stats(G) -> dict:
    """basic size numbers for a graph"""
    return {"nodes": G.number_of_nodes(), "edges": G.number_of_edges()}


# maps color number labels to actual display colors for visualization
color_map_dict = {
    0: "tab:red",
    1: "tab:orange",
    2: "tab:olive",
    3: "tab:green",
    4: "tab:blue",
    5: "tab:purple",
    6: "tab:brown",
    7: "tab:gray",
    8: "black"
}


def draw_graph(G, positions, coloring):
    # creates a list of the actual visualization colors in the correct order
    # (the modulo reuses colors if there are more color numbers than display colors)
    display_colors = list(color_map_dict.values())
    node_viz_colors = [display_colors[coloring[node] % len(display_colors)] for node in G.nodes()]


    # Below here all about drawing & displaying graph -------------------------

    # visualization graphics options
    options = {
        "font_size": 6,             # font size for labels
        "node_size": 150,           # size of node
        # "node_color": "yellow",   # node color (not to be used when dynamically coloring)
        "edgecolors": "black",
        "linewidths": 0,            # node border line width with 0=no border
        "width": 1,
    }

    # draw the graph

    # One of the two following options should be used:
    # nx.draw_networkx(G, positions, **options)             # allows labeling nodes and more options.  Slower
    nx.draw(G, positions, node_color=node_viz_colors, **options)                    # simple drawing function with no node labels.  Faster


    # if we wanted to place a image in the background, this would be used -----
    # load image from file for background
    # image = mpimg.imread('./images/background_image.jpg')

    # x_right = -73.70878
    # y_top = 40.92133
    # x_left = -74.301217
    # y_bottom = 40.482218

    # ax = plt.gca()
    # ax.imshow(image, aspect='auto', extent=[x_left, x_right, y_bottom, y_top] )

    plt.gca().set_aspect(1.2)    # sets output aspect ratio as 1:1
    # ax.margins(0.05)    # sets a margin around the plotted area
    # plt.axis(True)
    plt.show()


def main():
    parser = argparse.ArgumentParser(description="Color the US county adjacency graph")
    parser.add_argument("--strategy", default="dsatur", help="welsh_powell, dsatur, smallest_last, "
                        "independent_set (or any networkx strategy string with --impl networkx)")
    parser.add_argument("--impl", choices=["networkx", "local"], default="networkx",
                        help="networkx's code or our copies in greedy_coloring/")
    parser.add_argument("--no-plot", action="store_true", help="skip drawing the graph")
    parser.add_argument("--map", action="store_true",
                        help="draw a colored county map instead of the dot graph")
    args = parser.parse_args()

    # import data from files and create the graph
    G, positions = load_county_graph(verbose=True)
    print("Graph:", graph_stats(G))


    # Graph Coloring in this section ------------------------------------------
    print("Now calculating graph coloring.....")

    # Benchmarking start
    start_time = time.perf_counter()

    # Graph coloring here - select algorithm with --strategy
    node_color_label_dict = color_graph(G, args.strategy, args.impl)

    end_time = time.perf_counter()

    print("Number of colors used for Map Coloring: ", num_colors(node_color_label_dict))
    print("Coloring is valid: ", validate_coloring(G, node_color_label_dict))
    print(f"Elapsed time in seconds: {(end_time - start_time):.4f}")

    if args.no_plot:
        return
    if args.map:
        from visualize_map import draw_county_map       # needs numpy, downloads outlines once
        n = num_colors(node_color_label_dict)
        draw_county_map(node_color_label_dict, title=f"{args.strategy} ({args.impl}): {n} colors")
    else:
        draw_graph(G, positions, node_color_label_dict)


if __name__ == "__main__":
    main()
