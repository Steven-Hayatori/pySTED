from pySTED_generation import generation
import random
import simple_functions

NUM = 3

simple_functions.clearlog()

for i in range(NUM):
    STRENGTH_BG = random.randint(1, 4)
    STRENGTH_MO = random.randint(100, 300)
    NUM_MO = random.randint(20, 50)
    SEED_BG = random.randint(1, 1000)
    SEED_MO = random.randint(1, 1000)
    generation(STRENGTH_BG, STRENGTH_MO, NUM_MO, SEED_BG, SEED_MO, i)
simple_functions.log("Finished!")
