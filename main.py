import streamlit as st
from typing import List, Dict
import google.generativeai as genai
import os
import json
import re
from dotenv import load_dotenv
from pathlib import Path

# === SETUP ===
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

DATA_FILE = "data.json"

def user_already_exists(email: str, phone_number: str) -> bool:
    if Path(DATA_FILE).exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for record in data:
            if record["basic_info"].get("Email", "").lower() == email.lower() or record["basic_info"].get("Phone Number", "") == phone_number:
                return True
    return False

# === UTILITIES ===
def generate_questions(tech_stack: str) -> List[Dict[str, str]]:
    prompt = f"""
You are a technical interviewer. For each technology in the tech stack below, generate 3 relevant technical interview questions.

Tech Stack: {tech_stack}

Format response in JSON like:
{{
  "Python": ["Question1", "Question2", "Question3"],
  "React": ["Question1", "Question2", "Question3"]
}}
"""
    model = genai.GenerativeModel(model_name='gemini-1.5-flash')
    response = model.generate_content(prompt)

    try:
        clean_text = re.sub(r"```(?:json)?", "", response.text).strip("`\n ")
        parsed = json.loads(clean_text)
        questions = []
        for tech, qlist in parsed.items():
            for q in qlist:
                questions.append({"tech": tech, "question": q})
        return questions
    except Exception as e:
        st.error("❌ Error parsing AI response.")
        return []

def generate_feedback(answer: str, tech: str) -> str:
    prompt = f"""
    You are a technical interviewer. Based on the answer below for the {tech} question, generate a short and minimal constructive feedback.

    Answer: {answer}

    Provide feedback in a concise manner, no more than two lines.
    """

    model = genai.GenerativeModel(model_name='gemini-1.5-flash')
    response = model.generate_content(prompt)

    try:
        return response.text.strip()
    except Exception as e:
        st.error("❌ Error generating feedback.")
        return "No feedback available."

def save_to_json(candidate_data: Dict):
    if Path(DATA_FILE).exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = []

    data.append(candidate_data)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# === FORM FIELDS ===
form_fields = [
    "Full Name", "Email", "Phone Number", "Years of Experience",
    "Desired Position(s)", "Current Location", "Tech Stack"
]

# === FIELD VALIDATIONS ===
def is_valid_email(email: str) -> bool:
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", email))

def is_valid_phone(phone: str) -> bool:
    return bool(re.match(r"^\+?[1-9]\d{1,14}$", phone))  # A basic phone number validation (international format)

# === MAIN APP ===
def main():
    st.set_page_config(page_title="TalentScout", layout="centered")
    st.title("🤖 TalentScout - AI Hiring Assistant")

    if "step" not in st.session_state:
        st.session_state.step = 0
        st.session_state.answers = {}
        st.session_state.questions = []
        st.session_state.tech_answers = []
        st.session_state.feedbacks = []
        st.session_state.question_index = 0

    step = st.session_state.step
    total_steps = len(form_fields) + 2
    st.progress(min((step + 1) / total_steps, 1.0))

    # === Step-by-step form ===
    if step < len(form_fields):
        current_field = form_fields[step]
        with st.form(key="basic_form"):
            user_input = st.text_input(f"{current_field}:")
            submitted = st.form_submit_button("Next")
            if submitted:
                if not user_input.strip():
                    st.warning("Please enter a value.")
                else:
                    # Email Validation
                    if current_field == "Email" and not is_valid_email(user_input.strip()):
                        st.warning("Please enter a valid email address.")
                    # Phone Number Validation
                    elif current_field == "Phone Number" and not is_valid_phone(user_input.strip()):
                        st.warning("Please enter a valid phone number.")
                    # Duplicate Check for Email and Phone Number
                    elif current_field in ["Email", "Phone Number"]:
                        email = st.session_state.answers.get("Email", "")
                        phone = st.session_state.answers.get("Phone Number", "")
                        if user_already_exists(email, phone):
                            st.error("🚫 This email or phone number has already been used for screening.")
                            st.stop()

                    # Temporarily save input
                    st.session_state.answers[current_field] = user_input.strip()

                    st.session_state.step += 1
                    st.rerun()

    # === Generate questions ===
    elif step == len(form_fields):
        st.info("Generating questions based on your tech stack...")
        tech_stack = st.session_state.answers.get("Tech Stack", "")
        if tech_stack:
            st.session_state.questions = generate_questions(tech_stack)
            st.session_state.step += 1
            st.rerun()
        else:
            st.error("Tech Stack not found.")

    # === Show questions one-by-one ===
    elif step == len(form_fields) + 1:
        questions = st.session_state.questions
        q_index = st.session_state.question_index

        if q_index < len(questions):
            current_q = questions[q_index]
            st.subheader(f"🧠 {current_q['tech']} - Question {q_index + 1} of {len(questions)}")
            st.markdown(f"<ul><li>{current_q['question']}</li></ul>", unsafe_allow_html=True)

            with st.form(key=f"form_q{q_index}"):
                answer = st.text_area("Your Answer:")
                submitted = st.form_submit_button("Next Question")

                if submitted:
                    if not answer.strip():
                        st.warning("Answer is required.")
                    else:
                        # Generate feedback but don't show it to the user
                        feedback = generate_feedback(answer.strip(), current_q['tech'])

                        # Save answer and feedback for later
                        st.session_state.tech_answers.append({
                            "tech": current_q['tech'],
                            "question": current_q['question'],
                            "answer": answer.strip(),
                            "feedback": feedback  # Save feedback internally
                        })
                        st.session_state.feedbacks.append(feedback)
                        st.session_state.question_index += 1
                        st.rerun()
        else:
            st.session_state.step += 1
            st.rerun()

    # === Final Summary and Save to File ===
    else:
        st.success("🎉 Screening Complete!")

        st.markdown("### 👤 Your Info:")
        for k, v in st.session_state.answers.items():
            st.write(f"**{k}:** {v}")

        st.markdown("### 🧠 Technical Responses and Final Feedback:")
        for item in st.session_state.tech_answers:
            st.markdown(f"**🔹 {item['tech']}**")
            st.markdown(f"- **Q:** {item['question']}")
            st.markdown(f"- **A:** {item['answer']}")

        if st.button("Submit Final & Exit"):
            email = st.session_state.answers.get("Email", "")
            if user_already_exists(email, ""):
                st.warning("🚫 This user has already submitted their responses. Duplicate entries are not allowed.")
            else:
                candidate_data = {
                    "basic_info": st.session_state.answers,
                    "technical_answers": st.session_state.tech_answers
                }
                save_to_json(candidate_data)
                st.success("✅ Data submitted and saved! You can now close the app.")
                st.stop()

# === RUN ===
if __name__ == "__main__":
    main()
