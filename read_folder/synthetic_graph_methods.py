import matplotlib.pyplot as plt
import numpy as np
import networkx as nx
from scipy.spatial import Delaunay
import time

# NOTE: There are 2 methods of creating synthetic graphs below
# Code has to be manually adjusted to call the different methods
# The NUMBER_NODES variable controls the total nodes in the synthetic graph


# Synthetic Graph option 1: irregular triangles
def create_delaunay_triangle_planar_graph(number_nodes):
    """Returns a planar graph of irregular triangles using Delaunay triangulation"""

    rand_points = np.random.rand(number_nodes, 2)
    tri = Delaunay(rand_points)

    G = nx.Graph()
    for simplex in tri.simplices:
        nx.add_cycle(G, simplex)

    # Store the geometric coordinates as positions
    pos = {i: rand_points[i] for i in range(len(rand_points))}
    
    # Checks if the graph is indeed planar
    print("Is this graph planar? : ", "Yes" if nx.is_planar(G) else "No" ) 
    return G


# Synthetic Graph option 2: regular triangle lattice grid
def create_trianglular_grid(number_nodes):
    """Returns a planar triangle grid graph of roughly the number of nodes 
    becuase of structure of grid, will not be the exact number
    """

    rows = round(number_nodes ** 0.5)
    cols = round(number_nodes / rows) 
    G = nx.triangular_lattice_graph(m = rows - 1, n = cols * 2 - 1 )
    
    # Checks if the graph is indeed planar
    print("Is this graph planar? : ", "Yes" if nx.is_planar(G) else "No" ) 
    return G


# Create the graph using the different methods below ----------------------
# Change this number to adjust the number of nodes in the synthetic graphs
NUMBER_NODES = 30000

# G = create_trianglular_grid(NUMBER_NODES)
G = create_delaunay_triangle_planar_graph(NUMBER_NODES)


# Graph Coloring in this section ------------------------------------------
print("Now calculating graph coloring.....")

# Benchmarking start
start_time = time.perf_counter()

# Graph coloring here - select algorithm here
node_color_label_dict = nx.coloring.greedy_color(G, strategy='largest_first', interchange=False)

# Benchmarking end
end_time = time.perf_counter()

number_of_colors = max(node_color_label_dict.values()) + 1
print("Number of colors used for Map Coloring: ", number_of_colors)
print(f"Elapsed time in seconds: {(end_time - start_time):.4f}")
print(f"Number of Nodes in graph: {G.number_of_nodes()}")
print(f"Number of Edges in graph: {G.number_of_edges()}")



# Below relates to displaying a visualization of the graphs (unneeded for coloring time benchmarking)
# pos = nx.planar_layout(G)  # Guaranteed to work without edge crossings
# nx.draw(G, with_labels=True)
# plt.show()



# note: 
# these are the built-in greedy coloring strategies.  Will also accept a custom function
# https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.coloring.greedy_color.html
"""
'largest_first'     <-- * fastest
'random_sequential'
'smallest_last'     <-- * fast but lower colors
'independent_set'   <-- * slowest
'connected_sequential_bfs'
'connected_sequential_dfs'
'connected_sequential' # 
'saturation_largest_first'  <-- * good but slow
'DSATUR' # (alias for the previous strategy)
"""