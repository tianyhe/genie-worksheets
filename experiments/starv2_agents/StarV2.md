# StarV2 Tasks

1. There are 24 tasks in 13 domains. We already have some of the agents in `worksheets/agents` directory.
Most of them are complete. There are some agents that are not complete. You might want to complete them. The only thing left is adding few examples to:
- `worksheets/agents/<agent_name>/prompts/response_generation.prompts`
- `worksheets/agents/<agent_name>/prompts/semantic_parsing_stateless.prompts`
- `worksheets/agents/<agent_name>/prompts/semantic_parsing_stateful.prompts`

2. All the worksheets are here: https://drive.google.com/drive/folders/16Yvv7OxUuSewNHQXXKNlm21l-0mUHnY7?usp=sharing

3. To run the worksheets, you should create a google service account. I am sharing my credentials for now in the zip.

4. Download the StarV2 data from here: https://github.com/google-research/task-oriented-dialogue/tree/main/starv2

# Running the bot

```
python worksheets/main.py --domain <bot_folder_name>
```

# Running the bot with starV2

1. Use the `starv2_*.py` files. We have three files already: bank_fraud, trip and trivia.

2. You will mostly have to change the `load_state()` function that loads the state belief from StarV2 dialogue data.

3. Primarily need to change the `slot_to_worksheet` part, where slot-value pairs are turned into API (worksheet) and then executed.

4. You will also have to change the priority_queue. The queue is used to decide which API will be called first. Usually its the order of the worksheet in the spreadsheet. But for bank it is slightly different. The main is last and the rest are in order. (You can see the `baselines/starv2_bank_fraud_report.py` file for reference)

5. Earlier we were only calculating system accuracy. Now we are going to calculate all the metrics provided in ANYTOD. Just make sure that we are saving all the required information in the json file that will help in evaluate later.
