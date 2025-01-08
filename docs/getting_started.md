# Quickstart Guide

To create a conversational agent that guides conversations with a user to achieve a certain goal and answers 
users question, you need to provide Genie with:
- Worksheet: A high-level specification for guiding the conversation. Contains the tasks the agent can perform and 
knowledge sources available to the agent.
- Configuration: An entry python file that defines configuration for the agent.

## Creating a Worksheet
Our worksheet design is inspired by the versatility of webforms.
Modern websites contain multiple fields which can be optional, tabs for selection of task, and pop-up windows that 
depend on previous user responses. 
There are two kinds of worksheets: 

- task worksheet: To guide the conversation and achieve goals
- knowledge base worksheet: To answer users questions and assist them in making decisions.

### Task Worksheet
!!! tip "Example"
    Users perform different tasks based on their requirements. A student who is having trouble enrolling in a class 
    would need to fill out a form containing details about the course they want to enroll in, the error message they are
    seeing, and any other additional comments and tasks like Leave of Absence are irrelevant to them. We need to make
    relevant worksheets available.

#### Worksheet Attributes
A task worksheet has the following attributes for a Task worksheet:

- **WS Predicate**: indicates when a task worksheet should be activated based on values of other fields
- **WS Name**: the name of the worksheet. Used by semantic parser.
- **WS Kind**: Should be set to "Task". Defines that this is a Task type worksheet.
- **WS Actions**: Genie provides flexibility to the agent by executing arbitrary Python code to call external APIs, 
change assigned values, or explicitly respond to the user with a given string using built-in actions like say. 
The actions are triggered when all the required parameters for a task are assigned and are defined under WS Actions.

**WS Action examples**
Call external API to fetch information or post

!!! tip "Example for WS Action"
    Perform actions once the user has provided all the required information: If you want to book a restaurant, the agent will call the `book_restaurant` function.
    ```python
    book_restaurant(
        self.restaurant_name, 
        self.date, 
        self.num_people, 
        self.time, 
        self.special_instructions
    )
    ```

!!! tip "Example for Field Action"
    Perform task based on value of a field: Once the user provides the value for `confirm` field, the agent will say "Thank you".
    ```python
    if self.confirm:
        say("Thank you")
    ```

#### Field Attributes

Each task worksheet contains a set of fields. Each field contains the following attributes:

- **Predicate**: indicates when a field should be activated based on values of other fields
- **Kind**: three types of fields can be used: 
    - input: field values that are editable by the user
    - internal: field values that can only be edited by the agent
    - output: set according to the output of executing an API or knowledge base call
- **Types**: Genie allows standard types for each field [TODO: We only use type of guide the semantic parsing, think of them as type hints]: 
    - str: string type
    - bool: boolean type
    - int: integer type
    - float: float type
    - Enum: enumeration type. The values are set in Enum Values cells.
    - list: array of atomic types [TODO: Not implemented yet]
    - confirm: special type of boolean type, that prompts the user to confirm all the field values before performing 
    WS action.
- **Name**: Name of the field. Used by semantic parser.
- **Enum Values**: a set of Enum Values if the type of the field is `Enum`
- **Description**: provides a natural language description of the field.
- **Don't Ask**: a boolean that records the information if the user offers it, but the agent will not ask for it.
    If Don't Ask is false, the agent will ask for the field if it is not assigned, but user can refuse to answer if it
    is not Required.
- **Required**: if the field value is mandatory.
- **Confirmation**: asks for confirmation for the field value if set to TRUE.
- **Actions**: similar to WS Action, is used to execute python code to fetch, modify or post information.

### Knowledge Access Worksheet
Genie Worksheet treats knowledge access as a first-class object.

!!! tip "Example for knowledge access"
    Real-life queries often involve both structured and unstructured accesses.
    For instance, queries “What’s the best-rated restaurant with a romantic atmosphere” require access to both the 
    structured “ratings” column and the free text “reviews” column. 

To handle hybrid knowledge bases, Genie adopts the SUQL query language, an SQL extension that integrates search of
unstructured data (Liu et al., 2024d). Genie can be used with other knowledge access systems as well.

For each knowledge base to be included, the developer must create a worksheet with the following attributes:

- **WS Name**: the name of the worksheet. Used by semantic parser.
- **WS Kind**: Should be set to "KB". Defines that this is a Knowledge Base type worksheet.

The attributes for fields should be filled in as following:

- **Kind**: should always be set as `internal` since the user cannot make changes to theses fields. 
    Should also write `primary` if the field is a primary key as: `internal; primary`


## Creating Agents

For creating the agent, we need to load configurations, and add prompts.

1. First load the model configuration for different components of Genie Agent.

    ```python
    from yaml import safe_load

    with open("model_config.yaml", "r") as f:
        model_config = safe_load(f)
    ```

2. Define your Knowledge Sources. Right now Genie only supports SUQL knowledge base but in theory, Genie should work
with all the knowledge bases. SUQL uses PostgreSQL. You should first create a database in PostgreSQL.

    ```python
    from worksheets.knowledge import SUQLKnowledgeBase

    suql_knowledge = SUQLKnowledgeBase(
        llm_model_name="gpt-4o", # model name, append `azure/` or `together/` for azure and together models.
        tables_with_primary_keys={
            "restaurants": "_id", # table name and primary key
        },
        database_name="restaurants", # database name
        embedding_server_address="http://127.0.0.1:8509",  # embedding server address for free text type of KB Worksheet
        source_file_mapping={
            "course_assistant_general_info.txt": os.path.join(
                current_dir, "course_assistant_general_info.txt"
            ) # mapping of free-text files with the path
        },
        db_host="127.0.0.1", # database host (defaults)
        db_port="5432", # database port (defaults)
        postprocessing_fn=None,  # optional postprocessing function for SUQL query
        result_postprocessing_fn=None,  # optional result postprocessing function should return a dictionary
    )
    ```

    - Postprocessing function is used to modify the SUQL query before it is executed. For example, using `suql.agent.postprocess_suql` to hardcode the limit of the query to 3 and converting the location to longitude and latitude.
    - Result postprocessing function is used to clean up the result of the knowledge base call and return a dictionary. For example, if the knowledge base returns a list of restaurants, with 100s of columns, a function can be used to filter the required columns and return a dictionary.

3. Define your Knowledge Parser. Genie supports two types of semnatic parser for knowledge bases. React Multi-Agent 
Parser and a Simple LLM Parser.

    | Features | React Agent | Simple LLM Parser |
    |----------|-------------|-------------------|
    | Speed          | Slower          | Faster           |
    | Accuracy       | Better Accuracy | Worse            |
    | Needs Examples | No              | Yes              |


    **Defining a React Multi Agent Parser**

    ```python
    from worksheets.knowledge import SUQLReActParser

    suql_react_parser = SUQLReActParser(
        llm_model_name="azure/gpt-4o",  # model name
        example_path=os.path.join(current_dir, "examples.txt"),  # path to examples
        instruction_path=os.path.join(current_dir, "instructions.txt"),  # path to domain-specific instructions
        table_schema_path=os.path.join(current_dir, "table_schema.txt"),  # path to table schema
        knowledge=suql_knowledge,  # previously defined knowledge source
    )
    ```

    **Defining a Simple LLM Parser**


    ```python
    from worksheets.knowledge import SUQLParser

    suql_parser = SUQLParser(
        llm_model_name="azure/gpt-4o",
        prompt_selector=None,  # optional function that helps in selecting the right prompt
        knowledge=suql_knowledge,
    )
    ```

4. Bringing everything together

    ```python
    from worksheets.agent import Agent

    restaurant_bot = Agent(
        botname="YelpBot",  # Name of your agent
        description="You an assistant at Yelp and help users with all their queries related to booking a restaurant. You can search for restaurants, ask me anything about the restaurant and book a table.",
        prompt_dir=prompt_dir,  # directory for prompts
        starting_prompt="""Hello! I'm YelpBot. I'm here to help you find and book restaurants in four bay area cities **San Francisco, Palo Alto, Sunnyvale, and Cupertino**. What would you like to do?""",
        args={},  # additional arguments
        api=[book_restaurant_yelp],  # optional API functions
        knowledge_base=suql_knowledge,  # previously defined knowledge source
        knowledge_parser=suql_parser,  # previously defined knowledge parser
    ).load_from_gsheet(gsheet_id="ADD YOUR SPREADSHEET ID HERE",)
    ```

    The Genie Agent uses two prompts:

    - Semantic Parsing Prompt: This is used to generate worksheet representation of the user's query. The prompt directory should contain the `semantic_parser.prompt` file.
    - Response Generator Prompt: This is used to generate the response of the agent based on the worksheet representation and generated agent acts. The prompt directory should contain the `response_generator.prompt` file.

    Checkout how to create prompts in the [prompt section](./prompt.md).


5. Finally use the `converation_loop` funcion to run the agent

    ```python
    from asyncio import run
    from worksheets.interface_utils import conversation_loop

    asyncio.run(conversation_loop(restaurant_bot, output_state_path="yelp_bot.json"))
    ```

    Example agents are present in `experiments/agents/` directory. You can use them as a reference to create your own 
    agents.