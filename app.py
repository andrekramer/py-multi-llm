# partly generated by Gemini AI
from flask import Flask, request, render_template, jsonify

from multillm import run_comparison
from config import configure, web_comparisons

configure()

app = Flask(__name__)

@app.route('/prompt', methods=['POST'])
async def prompt():
    try:
        data = request.get_json()
        if not data or 'prompt' not in data:
            return jsonify({"error": "Invalid request: 'prompt' field is required."}), 400
        
        prompt = data['prompt']
        trail = await run_comparison(prompt, "3-way")

        response_text = trail[-1]
        response = {"response": response_text}
        return jsonify(response), 200

    except Exception as e:
      return jsonify({"error": f"Error processing the prompt: {str(e)}"}), 500


@app.route("/", methods=["GET", "POST"])
async def index():
    if request.method == "POST":
        input_text = request.form["text_input"]
        selected_comp = request.form.get("comp", "2")
        print("selected comp " + selected_comp)
        if input_text is None or input_text.strip() == "":
          return render_template("index.html", selected_comp=selected_comp, comps=web_comparisons)
        response_lines = await process_prompt(input_text, selected_comp)
        return render_template("index.html", response=response_lines, prompt=input_text, selected_comp=selected_comp, comps=web_comparisons) # Render the HTML page
    return render_template("index.html", selected_comp="2", comps=web_comparisons) # renders the page on a GET request


async def process_prompt(prompt, selected_comp):
  match selected_comp:
    case "0":
      comp = web_comparisons[0]
    case "1":
      comp = web_comparisons[1]
    case "2":
       comp = web_comparisons[2]
    case _:
       comp = "none"
  result = await run_comparison(prompt, comp) # respond with a list of strings
  return result

if __name__ == "__main__":
    app.run(debug=True)
