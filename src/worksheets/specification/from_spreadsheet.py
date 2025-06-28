import csv
import datetime
import json
from enum import Enum
from typing import List

from worksheets.core import GenieField
from worksheets.core.worksheet import Action, GenieDB, GenieType, GenieWorksheet
from worksheets.utils.field import get_genie_fields_from_ws
from worksheets.utils.gsheet import fill_all_empty, retrieve_gsheet

# Range of the gsheet
gsheet_range_default = "A1:AD1007"

# mapping of the columns
FORM_PREDICATE = 0
FORM_NAME = 1
FIELD_PREDICATE = 2
KIND = 3
FIELD_TYPE = 4
FIELD_NAME = 5
VARIABLE_ENUMS = 6
FIELD_DESCRIPTION = 7
DONT_ASK = 8
REQUIRED = 9
FIELD_CONFIRMATION = 10
FIELD_ACTION = 11
FORM_ACTION = 12
FIELD_VALIDATION = 13
EMPTY_COL = 14


def csv_to_classes(csv_path, **kwargs):
    """Convert a CSV file to Genie classes.

    Args:
        csv_path (str): The path to the CSV file.
    """
    rows = []
    with open(csv_path, "r") as file:
        reader = csv.reader(file)
        for row in reader:
            rows.append(row)

    return rows_to_classes(rows)


def gsheet_to_classes(gsheet_id, gsheet_range=gsheet_range_default, **kwargs):
    """Convert Google Sheets data to Genie classes.

    Args:
        gsheet_id (str): The ID of the Google Sheet.
        gsheet_range (str): The range of cells to retrieve.

    Yields:
        Tuple[str, type]: The type of the class and the class itself."""
    rows = retrieve_gsheet(gsheet_id, gsheet_range)
    return rows_to_classes(rows)


def json_to_classes(json_path, **kwargs):
    """Convert a JSON file to Genie classes.

    Args:
        json_path (str): The path to the JSON file.
    """
    with open(json_path, "r") as file:
        data = json.load(file)

    # Convert JSON data to the same format that rows_to_classes expects
    forms = []

    for worksheet in data:
        # Create form structure
        form_data = {
            "form": [
                worksheet.get("ws_predicate", "") or "",  # FORM_PREDICATE
                worksheet.get("ws_name", "") or "",  # FORM_NAME
                "",  # FIELD_PREDICATE (not used at form level)
                worksheet.get("ws_type", "") or "",  # KIND (worksheet/db/type)
                worksheet.get("ws_type", "") or "",  # FIELD_TYPE (same as ws_type)
                worksheet.get("ws_backend_api", "") or "",  # FIELD_NAME (backend_api)
                "",  # VARIABLE_ENUMS
                "",  # FIELD_DESCRIPTION
                "",  # DONT_ASK
                "",  # REQUIRED
                "",  # FIELD_CONFIRMATION
                worksheet.get("ws_actions", "") or "",  # FIELD_ACTION
                worksheet.get("ws_actions", "") or "",  # FORM_ACTION
                "",  # FIELD_VALIDATION
                "",  # EMPTY_COL
            ],
            "fields": [],
            "outputs": [],
        }

        # Process fields
        for field in worksheet.get("fields", []):
            # Handle enum values
            enum_values = field.get("enum_values", [])
            field_type = field.get("field_type", "")

            # If there are enum values, this is an Enum type
            if enum_values and isinstance(enum_values, list):
                field_type = "Enum"
                # Create enum class with the values
                enum_list = [
                    enum_item.get("value", "")
                    if isinstance(enum_item, dict)
                    else str(enum_item)
                    for enum_item in enum_values
                ]
                field_type = create_enum_class(field.get("field_name", ""), enum_list)

            # Determine if field is internal based on field_kind
            field_kind = field.get("field_kind", "input")
            is_internal = field_kind.lower() != "input"
            is_primary_key = "primary" in field_kind.lower()

            # Convert field to the expected format
            field_data = {
                "slottype": field_type,
                "name": field.get("field_name", "") or "",
                "description": field.get("field_description", "") or "",
                "predicate": field.get("field_predicate", "") or "",
                "ask": not field.get("field_dont_ask", False) or False,
                "optional": not field.get("field_required", False) or False,
                "actions": Action(field.get("field_actions", "") or ""),
                "value": None,
                "requires_confirmation": field.get("field_confirm") == "TRUE"
                or field.get("field_confirm") is True
                or False,
                "internal": is_internal or False,
                "primary_key": is_primary_key or False,
                "validation": None,  # Not present in JSON structure, can be added if needed
            }

            # Determine if this is an output field (could be based on field_kind or other criteria)
            if field_kind == "output":
                form_data["outputs"].append({"slottype": field_type})
            else:
                form_data["fields"].append(field_data)

        forms.append(form_data)

    # Now process forms similar to rows_to_classes
    for form in forms:
        class_name = form["form"][FORM_NAME].replace(" ", "")
        form_predicate = form["form"][FORM_PREDICATE]
        form_action = Action(form["form"][FORM_ACTION])
        backend_api = form["form"][FIELD_NAME]
        outputs = form["outputs"]
        fields = form["fields"]
        genie_type = form["form"][FIELD_TYPE].lower()
        yield create_class(
            class_name,
            fields,
            genie_type,
            form_predicate,
            form_action,
            backend_api,
            outputs,
        )


def rows_to_classes(rows):
    """Convert a list of rows to Genie classes.

    Args:
        rows (list): The list of rows.
    """
    if not rows:
        raise ValueError("No data found.")

    rows = fill_all_empty(rows, EMPTY_COL + 1)

    # removing headers from the CSV
    rows = rows[1:]

    # strip all the cells
    rows = [[cell.strip() for cell in row] for row in rows]

    # collecting all the rows
    forms = []
    i = 0
    while i < len(rows):
        enums = []
        if len(rows[i][FORM_NAME]):
            forms.append(
                {
                    "form": rows[i],
                    "fields": [],
                    "outputs": [],
                }
            )
        else:
            if rows[i][FIELD_TYPE] == "Enum":
                enum_idx = i + 1
                while (
                    enum_idx < len(rows)
                    and not len(rows[enum_idx][FIELD_TYPE].strip())
                    and not len(rows[enum_idx][FIELD_NAME].strip())
                ):
                    enums.append(rows[enum_idx][VARIABLE_ENUMS])
                    enum_idx += 1

            if rows[i][KIND] == "output":
                forms[-1]["outputs"].append({"slottype": rows[i][FIELD_TYPE]})
            else:
                forms[-1]["fields"].append(
                    {
                        "slottype": (
                            rows[i][FIELD_TYPE]
                            if rows[i][FIELD_TYPE] != "Enum"
                            else create_enum_class(rows[i][FIELD_NAME], enums)
                        ),
                        "name": rows[i][FIELD_NAME],
                        "description": rows[i][FIELD_DESCRIPTION],
                        "predicate": rows[i][FIELD_PREDICATE],
                        "ask": not rows[i][DONT_ASK] == "TRUE",
                        "optional": not rows[i][REQUIRED] == "TRUE",
                        "actions": Action(rows[i][FIELD_ACTION]),
                        "value": None,
                        "requires_confirmation": rows[i][FIELD_CONFIRMATION] == "TRUE",
                        "internal": False if rows[i][KIND].lower() == "input" else True,
                        "primary_key": (
                            True if "primary" in rows[i][KIND].lower() else False
                        ),
                        "validation": (
                            None
                            if len(rows[i][FIELD_VALIDATION].strip()) == 0
                            else rows[i][FIELD_VALIDATION]
                        ),
                    }
                )
        if len(enums):
            i = enum_idx
        else:
            i += 1

    # creating the genie worksheet
    for form in forms:
        class_name = form["form"][FORM_NAME].replace(" ", "")
        form_predicate = form["form"][FORM_PREDICATE]
        form_action = Action(form["form"][FORM_ACTION])
        backend_api = form["form"][FIELD_NAME]
        outputs = form["outputs"]
        fields = form["fields"]
        genie_type = form["form"][FIELD_TYPE].lower()
        yield create_class(
            class_name,
            fields,
            genie_type,
            form_predicate,
            form_action,
            backend_api,
            outputs,
        )


# Function to dynamically create a class based on a dictionary
def create_class(
    class_name,
    fields,
    genie_type,
    form_predicate,
    form_action,
    backend_api,
    outputs,
):
    """Create a class dynamically based on the provided parameters.

    Args:
        class_name (str): The name of the class to create.
        fields (list): A list of field dictionaries.
        genie_type (str): The type of the Genie class (worksheet, db, type).
        form_predicate (str): The predicate for the form.
        form_action (Action): The action associated with the form.
        backend_api (str): The backend API associated with the form.
        outputs (list): A list of output dictionaries.

    Returns:
        Tuple[str, type]: The type of the class and the class itself."""

    # Create a dictionary for class attributes
    class_dict = {}
    for field_dict in fields:
        # Here, you would handle custom field types or validations
        class_dict[field_dict["name"]] = GenieField(**field_dict)

    if genie_type == "worksheet":
        class_dict["predicate"] = form_predicate
        class_dict["outputs"] = [output["slottype"] for output in outputs]
        class_dict["actions"] = form_action
        class_dict["backend_api"] = backend_api
        return (genie_type, type(class_name, (GenieWorksheet,), class_dict))
    elif genie_type == "db":
        class_dict["outputs"] = [output["slottype"] for output in outputs]
        class_dict["actions"] = form_action
        return (genie_type, type(class_name, (GenieDB,), class_dict))
    elif genie_type == "type":
        class_dict["predicate"] = form_predicate
        class_dict["actions"] = form_action
        return (genie_type, type(class_name, (GenieType,), class_dict))


def create_enum_class(class_name, enums):
    """Create an Enum class dynamically

    Args:
        class_name (str): The name of the Enum class.
        enums (list): A list of enum values.

    Returns:
        Enum: The created Enum class."""

    enums = [e.strip() for e in enums if len(e.strip())]
    return Enum(convert_snake_to_camel_case(class_name), enums)


def convert_snake_to_camel_case(snake_str: str):
    """Convert a snake_case string to camelCase.

    Args:
        snake_str (str): The snake_case string to convert.

    Returns:
        str: The converted camelCase string.
    """
    components = snake_str.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


str_to_type = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "date": datetime.date,
    "time": datetime.time,
}


def specification_to_genie(
    csv_path: str | None = None,
    gsheet_id: str | None = None,
    json_path: str | None = None,
    gsheet_range: str = gsheet_range_default,
):
    """Convert a specification to Genie components that are used to create the agent

    Args:
        csv_path (str): The path to the CSV file.
        gsheet_id (str): The ID of the Google Sheet.
        json_path (str): The path to the JSON file.
        gsheet_range (str): The range of cells to retrieve.
    """

    if csv_path:
        to_classes_func = csv_to_classes
        kwargs = {"csv_path": csv_path}
    elif gsheet_id:
        to_classes_func = gsheet_to_classes
        kwargs = {"gsheet_id": gsheet_id, "gsheet_range": gsheet_range}
    elif json_path:
        to_classes_func = json_to_classes
        kwargs = {"json_path": json_path}
    else:
        raise ValueError("Either csv_path, gsheet_id, or json_path must be provided")

    genie_worsheets = []
    genie_worsheets_names = {}
    genie_dbs = []
    genie_dbs_names = {}
    genie_types = []
    genie_types_names = {}
    for genie_type, cls in to_classes_func(**kwargs):
        if genie_type == "worksheet":
            genie_worsheets.append(cls)
            genie_worsheets_names[cls.__name__] = cls
        elif genie_type == "db":
            genie_dbs.append(cls)
            genie_dbs_names[cls.__name__] = cls
        elif genie_type == "type":
            genie_types.append(cls)
            genie_types_names[cls.__name__] = cls

    for worksheet in genie_worsheets + genie_dbs + genie_types:
        for field in get_genie_fields_from_ws(worksheet):
            if isinstance(field.slottype, str):
                if field.slottype in str_to_type:
                    field.slottype = str_to_type[field.slottype]
                elif field.slottype == "confirm":
                    field.slottype = "confirm"
                elif field.slottype == "Enum":
                    field.slottype = Enum(field.name, field.slottype[1])
                elif field.slottype.startswith("List"):
                    if field.slottype[5:-1] in genie_types_names:
                        field.slottype = List[genie_types_names[field.slottype[5:-1]]]
                    elif field.slottype[5:-1] in genie_dbs_names:
                        field.slottype = List[genie_dbs_names[field.slottype[5:-1]]]
                    elif field.slottype[5:-1] in genie_worsheets_names:
                        field.slottype = List[
                            genie_worsheets_names[field.slottype[5:-1]]
                        ]
                    else:
                        if field.slottype[5:-1] in str_to_type:
                            field.slottype = List[str_to_type[field.slottype[5:-1]]]
                        else:
                            raise ValueError(f"Unknown type {field.slottype}")
                elif field.slottype in genie_types_names:
                    field.slottype = genie_types_names[field.slottype]
                elif field.slottype in genie_dbs_names:
                    field.slottype = genie_dbs_names[field.slottype]
                elif field.slottype in genie_worsheets_names:
                    field.slottype = genie_worsheets_names[field.slottype]
                else:
                    raise ValueError(f"Unknown type {field.slottype}")

    for ws in genie_dbs + genie_worsheets:
        for output in ws.outputs:
            if output in genie_worsheets_names:
                ws.outputs[ws.outputs.index(output)] = genie_worsheets_names[output]
            elif output in genie_types_names:
                ws.outputs[ws.outputs.index(output)] = genie_types_names[output]
            else:
                if output in str_to_type:
                    ws.outputs[ws.outputs.index(output)] = str_to_type[output]
                else:
                    raise ValueError(f"Unknown type {output}")

    return genie_worsheets, genie_dbs, genie_types
