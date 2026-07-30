"""Expand Value Questions pools so each survey can sample different sets of 5."""

import frappe

CATEGORIES = [
	"Communication",
	"Leadership",
	"Problem Solving",
	"Teamwork",
	"Technical Skills",
]

QUESTIONS_BY_CATEGORY = {
	"Communication": [
		"Adapts communication style to different audiences",
		"Writes clear and professional emails and reports",
		"Provides timely and constructive feedback",
		"Actively listens to others' input and feedback",
		"Communicates ideas clearly and concisely",
		"Presents information confidently in meetings and discussions",
		"Explains complex information in an understandable manner",
		"Encourages open and honest communication",
		"Responds appropriately to questions and concerns",
		"Maintains professionalism in verbal communication",
		"Seeks clarification when information is unclear",
		"Shares relevant information promptly with stakeholders",
		"Demonstrates strong presentation skills",
		"Communicates effectively during difficult situations",
		"Ensures key messages are understood by others",
		"Adjusts communication methods to suit the situation",
		"Uses examples effectively to explain concepts",
		"Provides updates on progress in a timely manner",
		"Demonstrates confidence when communicating with senior leaders",
		"Communicates expectations clearly to others",
		"Uses appropriate tone and language in communication",
		"Encourages participation in discussions",
		"Handles sensitive conversations professionally",
		"Communicates changes effectively to affected parties",
		"Demonstrates empathy during conversations",
		"Provides clear instructions for assigned tasks",
		"Effectively summarizes discussions and decisions",
		"Builds understanding through effective questioning",
		"Communicates effectively across departments",
		"Maintains transparency when sharing information",
	],
	"Leadership": [
		"Makes sound decisions under pressure",
		"Leads by example and maintains high standards",
		"Effectively delegates tasks and responsibilities",
		"Takes initiative in challenging situations",
		"Demonstrates ability to guide and inspire the team",
		"Encourages accountability and ownership among team members",
		"Builds trust within the team",
		"Handles challenges with confidence and composure",
		"Provides clear direction and expectations",
		"Supports team members in achieving their goals",
		"Motivates others to perform at their best",
		"Demonstrates integrity in decision-making",
		"Promotes a positive and productive work environment",
		"Recognizes and appreciates team contributions",
		"Manages change effectively within the team",
		"Coaches others to improve performance",
		"Encourages innovation and new ideas",
		"Addresses performance issues constructively",
		"Balances organizational goals with team needs",
		"Maintains focus during periods of uncertainty",
		"Builds commitment to team objectives",
		"Demonstrates fairness when making decisions",
		"Empowers others to take responsibility",
		"Provides support during organizational changes",
		"Develops future leaders within the team",
		"Communicates a clear vision for success",
		"Manages resources effectively to achieve objectives",
		"Encourages collaboration across teams",
		"Demonstrates resilience during setbacks",
		"Fosters a culture of continuous improvement",
	],
	"Problem Solving": [
		"Evaluates outcomes and learns from experience",
		"Implements solutions efficiently",
		"Develops creative and practical solutions",
		"Analyzes root causes effectively",
		"Identifies problems proactively",
		"Uses data and evidence to support decision-making",
		"Considers multiple alternatives before acting",
		"Anticipates potential obstacles and risks",
		"Breaks complex issues into manageable components",
		"Makes effective decisions with limited information",
		"Adapts solutions when circumstances change",
		"Balances short-term and long-term considerations",
		"Prioritizes problems based on impact and urgency",
		"Demonstrates critical thinking when evaluating options",
		"Continuously seeks opportunities for improvement",
		"Identifies patterns and trends in available information",
		"Evaluates risks before implementing solutions",
		"Tests solutions before full implementation where appropriate",
		"Remains objective when analyzing issues",
		"Applies lessons learned from previous experiences",
		"Effectively gathers information needed for decisions",
		"Recognizes potential issues before they escalate",
		"Develops contingency plans for critical situations",
		"Selects practical solutions aligned with objectives",
		"Uses logical reasoning to resolve challenges",
		"Measures the effectiveness of implemented solutions",
		"Seeks input from others when solving complex problems",
		"Evaluates the impact of decisions on stakeholders",
		"Maintains focus when dealing with difficult problems",
		"Improves existing processes through problem analysis",
	],
	"Teamwork": [
		"Contributes positively to team morale",
		"Resolves conflicts constructively",
		"Supports colleagues in achieving team goals",
		"Shares knowledge and resources willingly",
		"Collaborates effectively with team members",
		"Demonstrates respect for diverse perspectives and opinions",
		"Participates actively in team discussions",
		"Encourages cooperation among team members",
		"Values and acknowledges others' contributions",
		"Builds positive working relationships",
		"Helps create an inclusive team environment",
		"Offers assistance when colleagues need support",
		"Works effectively across departments or functions",
		"Prioritizes team success alongside individual success",
		"Accepts and acts on team feedback constructively",
		"Demonstrates reliability in fulfilling team commitments",
		"Supports team decisions once agreed upon",
		"Encourages open communication within the team",
		"Actively contributes ideas during collaborative activities",
		"Maintains positive relationships during disagreements",
		"Recognizes the strengths of team members",
		"Works effectively with people from different backgrounds",
		"Promotes trust among team members",
		"Encourages mutual respect within the team",
		"Contributes to a positive and supportive work culture",
		"Demonstrates flexibility when working with others",
		"Helps resolve misunderstandings promptly",
		"Voluntarily assists colleagues during busy periods",
		"Shares credit fairly for team achievements",
		"Contributes to achieving shared team objectives",
	],
	"Technical Skills": [
		"Shares technical expertise with the team",
		"Produces high-quality technical output",
		"Applies technical knowledge to solve problems",
		"Keeps up to date with industry developments",
		"Demonstrates proficiency in required technical areas",
		"Learns and adopts new tools technologies or methods effectively",
		"Demonstrates attention to technical accuracy",
		"Uses appropriate tools and technologies efficiently",
		"Troubleshoots technical issues effectively",
		"Applies best practices in daily work",
		"Understands the technical requirements of assigned tasks",
		"Continuously develops professional knowledge and skills",
		"Adapts technical skills to changing business needs",
		"Delivers work that meets technical standards and expectations",
		"Provides technical guidance when needed",
		"Produces reliable and accurate technical results",
		"Demonstrates strong analytical technical abilities",
		"Maintains technical documentation effectively",
		"Applies technical standards consistently",
		"Uses technology to improve efficiency and effectiveness",
		"Quickly learns unfamiliar technical concepts",
		"Identifies opportunities for technical improvements",
		"Effectively evaluates technical solutions and tools",
		"Ensures technical work complies with requirements",
		"Demonstrates competence in specialized technical tasks",
		"Applies technical expertise to support organizational goals",
		"Contributes to technical innovation and improvement",
		"Maintains awareness of emerging technologies",
		"Transfers technical knowledge to colleagues effectively",
		"Demonstrates confidence in handling technical challenges",
	],
}


def execute():
	for category in CATEGORIES:
		if not frappe.db.exists("Value Performance Categories", category):
			frappe.get_doc(
				{"doctype": "Value Performance Categories", "name1": category}
			).insert(ignore_permissions=True)

		existing = {
			(row.question or "").strip()
			for row in frappe.get_all(
				"Value Questions",
				filters={"category": category},
				fields=["question"],
			)
		}

		for question in QUESTIONS_BY_CATEGORY[category]:
			question = (question or "").strip()
			if not question or question in existing:
				continue

			frappe.get_doc(
				{
					"doctype": "Value Questions",
					"category": category,
					"question": question,
				}
			).insert(ignore_permissions=True)
			existing.add(question)

	if frappe.db.exists("DocType", "Value Scoring Settings") and frappe.db.exists(
		"Value Scoring Settings", "Value Scoring Settings"
	):
		current = frappe.db.get_value(
			"Value Scoring Settings", "Value Scoring Settings", "questions_per_category"
		)
		if not current or int(current) != 5:
			frappe.db.set_value(
				"Value Scoring Settings",
				"Value Scoring Settings",
				"questions_per_category",
				5,
				update_modified=False,
			)
