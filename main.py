import streamlit as st
from typing import List, Dict
import google.generativeai as genai
import os
import json
import re
from dotenv import load_dotenv
from pathlib import Path
from pymongo import MongoClient

# Load environment variables
load_dotenv()

# Configure Gemini API and MongoDB
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
client = MongoClient(os.getenv("MONGO_URI"))
db = client["talentScoutDB"]
collection = db["candidates"]

# Form field order
form_fields = [
    "Full Name", "Email", "Phone Number", "Years of Experience",
    "Desired Position(s)", "Current Location", "Tech Stack"
]

# ======================= Validation Functions ========================
def is_valid_name(name: str) -> bool:
    return bool(re.match(r"^[A-Za-z ]{2,50}$", name.strip()))

def is_valid_email(email: str) -> bool:
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", email.strip()))

def is_valid_phone(phone: str) -> bool:
    return bool(re.match(r"^\+?[1-9]\d{1,14}$", phone.strip()))

def is_valid_experience(exp: str) -> bool:
    try:
        val = float(exp)
        return 0 <= val <= 50
    except ValueError:
        return False

def user_already_exists(email: str, phone_number: str) -> bool:
    return collection.find_one({
        "$or": [
            {"basic_info.Email": {"$regex": f"^{email}$", "$options": "i"}},
            {"basic_info.Phone Number": phone_number}
        ]
    }) is not None

# ======================= Gemini AI Functions ========================
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
    except Exception:
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
    except Exception:
        st.error("❌ Error generating feedback.")
        return "No feedback available."

def calculate_score(answers: List[Dict]) -> int:
    score = 0
    for item in answers:
        answer_len = len(item["answer"].strip())
        if answer_len > 100:
            score += 3
        elif answer_len > 50:
            score += 2
        elif answer_len > 20:
            score += 1

    total_possible = len(answers) * 3
    percentage = round((score / total_possible) * 100) if total_possible else 0
    return percentage

def save_to_mongo(candidate_data: Dict):
    collection.insert_one(candidate_data)

# ======================= Main Streamlit App ========================
def main():
    st.set_page_config(page_title="SkillMatch AI", layout="centered")
    st.title("🧑‍💼 SkillMatch AI - Smart Hiring Assistant")

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

    # ======================== Form Steps ========================
    if step < len(form_fields):
        current_field = form_fields[step]
        with st.form(key="basic_form"):
            user_input = st.text_input(f"{current_field}:")
            submitted = st.form_submit_button("Next")

            if submitted:
                user_input = user_input.strip()
                if not user_input:
                    st.warning("Please enter a value.")
                else:
                    # Field-specific validation
                    if current_field == "Full Name" and not is_valid_name(user_input):
                        st.warning("Please enter a valid name.")
                        return
                    if current_field == "Email":
                        if not is_valid_email(user_input):
                            st.warning("Please enter a valid email address.")
                            return
                        elif user_already_exists(user_input, ""):
                            st.error("🚫 This email has already been used.")
                            st.stop()
                    if current_field == "Phone Number":
                        if not is_valid_phone(user_input):
                            st.warning("Please enter a valid phone number.")
                            return
                        email = st.session_state.answers.get("Email", "")
                        if user_already_exists(email, user_input):
                            st.error("🚫 This phone number is already used.")
                            st.stop()
                    if current_field == "Years of Experience" and not is_valid_experience(user_input):
                        st.warning("Please enter a valid experience (0–50 years).")
                        return

                    st.session_state.answers[current_field] = user_input
                    st.session_state.step += 1
                    st.rerun()

    # ======================== Question Generation ========================
    elif step == len(form_fields):
        st.info("Generating questions based on your tech stack...")
        tech_stack = st.session_state.answers.get("Tech Stack", "")
        if tech_stack:
            st.session_state.questions = generate_questions(tech_stack)
            st.session_state.step += 1
            st.rerun()
        else:
            st.error("Tech Stack not found.")

    # ======================== Answering Questions ========================
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
                        feedback = generate_feedback(answer.strip(), current_q['tech'])

                        st.session_state.tech_answers.append({
                            "tech": current_q['tech'],
                            "question": current_q['question'],
                            "answer": answer.strip(),
                            "feedback": feedback
                        })
                        st.session_state.feedbacks.append(feedback)
                        st.session_state.question_index += 1
                        st.rerun()
        else:
            st.session_state.step += 1
            st.rerun()

    # ======================== Final Screen ========================
    else:
        st.success("🎉 Screening Complete!")

        st.markdown("### 👤 Your Info:")
        for k, v in st.session_state.answers.items():
            st.write(f"**{k}:** {v}")

        st.markdown("### 🧠 Technical Responses and Feedback:")
        for item in st.session_state.tech_answers:
            st.markdown(f"**🔹 {item['tech']}**")
            st.markdown(f"- **Q:** {item['question']}")
            st.markdown(f"- **A:** {item['answer']}")
            st.markdown(f"- **💬 Feedback:** {item['feedback']}")

        overall_score = calculate_score(st.session_state.tech_answers)
        st.markdown(f"### 📈 Overall Technical Score: **{overall_score}%**")

        if st.button("Submit Final & Exit"):
            email = st.session_state.answers.get("Email", "")
            phone = st.session_state.answers.get("Phone Number", "")
            if user_already_exists(email, phone):
                st.warning("🚫 This user has already submitted their responses.")
            else:
                candidate_data = {
                    "basic_info": st.session_state.answers,
                    "technical_answers": st.session_state.tech_answers,
                    "score_percent": overall_score
                }
                save_to_mongo(candidate_data)
                st.success("✅ Data submitted and saved! You can now close the app.")
                st.stop()

# Run the app
if __name__ == "__main__":
    main()
