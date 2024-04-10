from pySTED_generation import generation
import random
import simple_functions

NUM = 4000 # 打算生成的张数
START_i = 205 #已经有的张数（不用算了直接写“总数”或者“最后一张index+1”），会有一张重复

simple_functions.clearlog()

for i in range(NUM):
    number = i + START_i + 1
    STRENGTH_BG = random.randint(1, 4)
    STRENGTH_MO = random.randint(100, 300)
    NUM_MO = random.randint(20, 50)
    SEED_BG = random.randint(1, 100000)
    SEED_MO = random.randint(1, 100000)
    generation(STRENGTH_BG, STRENGTH_MO, NUM_MO, SEED_BG, SEED_MO, number)
simple_functions.log("Finished!")
