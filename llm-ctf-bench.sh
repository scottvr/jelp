# required, number of times the select scenarios (or full harness) will run, logging to the same output file
ITERATIONS=3
MAX_STEPS=12
export MAX_STEPS

# optional, to run anything less thann the full fixture suits
# export SUBSET="--scenario fixture01_vault"
MODES="--modes help-only help-only-primed jelp-primed-useful jelp-primed-incremental jelp-primed-full"

# quick hack for adding SUB to logfiles. I should probably just timesstamp the logfiles and add a header row for the metadata for quick grepping/heading of logfiles to find relevant ones.
SUBN=$(echo ${SUBSET} | awk '{ print $NF }')


export MODES


export DEBUG="--debug"

### gpt-4.1-mini ###
MODEL="gpt-4.1-mini"
export MODEL

TEMPERATURE="0.2"
export TEMPERATURE

PYTHONPATH=src:. .venv/bin/python ctf/harness.py ${DEBUG} --adapter openai --model gpt-4.1-mini --modes jelp-primed-incremental jelp-primed-full --iterations 3 --temperature ${TEMPERATURE}  --max-steps ${MAX_STEPS}  --api-timeout-s 45 --response-max-output-tokens 1200 --adapter-retries 1 --out ctf/results/openai-gpt-4.1-mini-temp-${TEMPERATURE}-primed-modes-${SUBN}-steps-${MAX_STEPS}_${ITERATIONS}runs.json --iterations  ${ITERATIONS} ${MODES} ${SUBSET}

#PYTHONPATH=src:. .venv/bin/python ctf/harness.py --adapter openai --model ${MODEL} --debug --api-timeout-s 45 --response-max-output-tokens 500 --adapter-retries 1 --temperature 0.1 --iterations $ITERATIONS --out ctf/results/openai-${MODEL}-temperature_0.1-${ITERATIONS}runs.json  --max-steps 12 ${MODES} ${SUBSET}

#PYTHONPATH=src:. .venv/bin/python ctf/harness.py --adapter openai --model gpt-4.1-mini --modes jelp-primed-incremental jelp-primed-full --iterations ${ITERATIONS} --max-steps 12 --out ctf/results/openai-primed-jelp-only-${ITERAATIONS}runs.json ${MODES} ${SUBSET}


# PYTHONPATH=src:. .venv/bin/python ctf/harness.py --adapter openai --model gpt-4.1-mini --debug --api-timeout-s 45 --response-max-output-tokens 500 --adapter-retries 1 --max-steps 12

# PYTHONPATH=src:. .venv/bin/python ctf/harness.py --adapter openai --model ${MODEL} --debug --api-timeout-s 45 --response-max-output-tokens 500  --adapter-retries 1  --out ctf/results/openai-${MODEL}.json  --max-steps 12 ${SUBSET}


# FYI Temperature at 1.9 yields bonnkers responses from 4.1-mini
# PYTHONPATH=src:. .venv/bin/python ctf/harness.py --adapter openai --model  ${MODEL} --debug --api-timeout-s 45 --response-max-output-tokens 500 --adapter-retries 1 --temperature 1.0 --out ctf/results/openai-${MODEL}-temperature_1.0.json  --max-steps 12 ${SUBSET}


### gpt-5-mini ###
export MODEL="gpt-5-mini"

# PYTHONPATH=src:. .venv/bin/python ctf/harness.py --adapter openai --model ${MODEL}  --debug --api-timeout-s 45 --response-max-output-tokens 1500 --adapter-retries 1 --out ctf/results/openai-${MODEL}.json  --max-steps 12 ${SUBSET}


### gpt-5 ###
export MODEL="gpt-5-2025-08-07"

#PYTHONPATH=src:. .venv/bin/python ctf/harness.py --adapter openai --model ${MODEL}  --debug --api-timeout-s 45 --response-max-output-tokens 1500 --adapter-retries 1 --out ctf/results/openai-${MODEL}.json  --max-steps 12 ${SUBSET}
