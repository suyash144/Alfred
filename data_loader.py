import numpy as np

###############################################################################
# Initialize example data
###############################################################################
def initialize_data():
    global analysis_namespace
    
    c1 = [[1, 0.8, 0],
          [0.8, 1, 0],
          [0, 0, 1]]
    c2 = [[1, 0, 0],
          [0, 1, -0.8],
          [0, -0.8, 1]]
    m1 = [0, 0, 0]
    m2 = [5, 0, 0]

    # Generate two sets of points from multivariate normals, then concatenate
    x = np.concatenate((
        np.random.multivariate_normal(m1, c1, 500),
        np.random.multivariate_normal(m2, c2, 500)
    ))

    data_inventory = "Available data variables:\n"
    data_inventory += f"- x: {x.shape}\n"
    
    return x, data_inventory