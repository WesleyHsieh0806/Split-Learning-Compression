# Run all the experiments (different cut layer)
for cutlayer in $(seq 1 5)
do 
    python train_cut.py --cut ${cutlayer}
done