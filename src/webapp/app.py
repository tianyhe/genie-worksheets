import ast
import traceback

from flask import Flask, jsonify, render_template, request

from worksheets.specification.from_spreadsheet import gsheet_to_genie

app = Flask(__name__, static_folder="static", template_folder="templates")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/validate_syntax", methods=["POST"])
def validate_syntax():
    try:
        data = request.json
        code = data.get("code", "")
        field_type = data.get("fieldType", "code")  # predicate or action

        # Handle empty code
        if not code.strip():
            return jsonify({"isValid": True, "suggestions": []})

        # Try to parse the Python code
        ast.parse(code)

        # Additional validation based on field type
        if field_type == "predicate":
            # Allow True and False literals
            if code.strip() in ["True", "False"]:
                return jsonify({"isValid": True, "suggestions": []})

            # Predicates should typically be expressions that return a boolean
            if not any(
                keyword in code.lower()
                for keyword in ["==", "!=", ">", "<", ">=", "<=", "in", "is"]
            ):
                return jsonify(
                    {
                        "isValid": False,
                        "error": "Predicate should contain a comparison operator (==, !=, >, <, >=, <=, in, is) or be True/False",
                        "suggestions": [
                            "Use comparison operators (==, !=, >, <, >=, <=)",
                            "Check if a value is in a collection using 'in'",
                            "Compare identity using 'is'",
                            "Use True or False for constant predicates",
                        ],
                    }
                )
        elif field_type == "action":
            # Actions should typically modify state or return a value
            if not any(
                keyword in code for keyword in ["=", "return", "yield", "raise"]
            ):
                return jsonify(
                    {
                        "isValid": False,
                        "error": "Action should contain an assignment or return statement",
                        "suggestions": [
                            "Assign values using '='",
                            "Return values using 'return'",
                            "Use 'raise' for exceptions",
                        ],
                    }
                )

        return jsonify({"isValid": True, "suggestions": []})
    except SyntaxError as e:
        error_line = e.text.strip() if e.text else ""
        offset = e.offset - 1 if e.offset else 0
        pointer = " " * offset + "^"

        suggestions = []
        if "EOF" in str(e):
            suggestions.append("Add missing closing parenthesis/bracket/quote")
        elif "invalid syntax" in str(e):
            if ":" in error_line:
                suggestions.append(
                    "Check if you're using Python keywords correctly (if, for, while, etc.)"
                )
            if "=" in error_line:
                suggestions.append("For comparison use '==' instead of '='")
        elif "unexpected indent" in str(e):
            suggestions.append("Remove extra indentation")
        elif "unindent" in str(e):
            suggestions.append("Fix indentation to match the code block")

        return jsonify(
            {
                "isValid": False,
                "error": str(e),
                "errorLine": error_line,
                "errorPointer": pointer,
                "suggestions": suggestions,
            }
        )
    except Exception as e:
        error_info = traceback.format_exc()
        suggestions = []

        if "NameError" in error_info:
            suggestions.append("Define all variables before using them")
        elif "TypeError" in error_info:
            suggestions.append("Check if you're using compatible types")
        elif "IndentationError" in error_info:
            suggestions.append("Fix the indentation of your code")

        return jsonify({"isValid": False, "error": str(e), "suggestions": suggestions})


@app.route("/process_sheet", methods=["POST"])
def process_sheet():
    try:
        data = request.json
        sheet_data = data["sheetData"]

        # Convert the sheet data to a format compatible with gsheet_to_genie
        # This is a placeholder - you'll need to implement the actual conversion
        # based on your specific needs

        # Process the data using existing logic
        worksheets, dbs, types = gsheet_to_genie(sheet_data)

        return jsonify(
            {
                "status": "success",
                "message": "Sheet processed successfully",
                "worksheets": len(worksheets),
                "dbs": len(dbs),
                "types": len(types),
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


if __name__ == "__main__":
    app.run(debug=True, port=9898)
