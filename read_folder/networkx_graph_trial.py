# Notes: requires networkx library
# works with Python ver 3.14, possibly earlier versions as well

import networkx as nx               # networkx used for making graph
import matplotlib.pyplot as plt     # matplotlib used for plotting data in visual graphic
import matplotlib.image as mpimg    # used to show background image


def import_data() -> tuple[dict, list]:
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
    county_loc_file = open('./data/county_locations_cleanedRL.csv', 'r')
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

    county_loc_file.close()
    print("location file counties imported: ", line_number)

    
    # Import county adjacency (neighbor borders) data from file, add lat and long info ------------
    # This represents Edges on a graph
    county_adj_data = []
    county_adj_file = open('./data/county_adjacency_cleanedRL.txt', "r")
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
            print(f"KeyError: {e} County Geoid from Adj file not found in lat/long file")
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

    county_adj_file.close()
    print("Number of KeyErrors: ", key_errors)
    print("Adjacency file counties imported: ", line_number)


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



def main():
    # create empty graph
    G = nx.Graph()

    # import data from files
    county_locations, county_adj_data = import_data()

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



    # Below here all about drawing & displaying graph -------------------------
    
    # visualization graphics options
    options = {
        "font_size": 6,
        "node_size": 250,
        "node_color": "yellow",
        "edgecolors": "black",
        "linewidths": 1,
        "width": 1,
    }

    # draw the graph

    # One of the two following options should be used:
    nx.draw_networkx(G, positions, **options)             # allows labeling nodes and more options.  Slower
    # nx.draw(G, positions, **options)                    # simple drawing function with no node labels.  Faster


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
    plt.axis(True)
    plt.show()


main()

