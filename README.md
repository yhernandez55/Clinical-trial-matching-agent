# Clinical-trial-matching-agent


## Description: 
A clinical trial shouldn’t require a law degree and an insurance broker to find. Patients searching for trials face two walls: dense eligibility criteria scattered about, and no way to know whether their insurance would cover the visits involved. This agent does both—it matches a patient’s plain-language description of their condition to real trial criteria, and then checks that match against their coverage so they walk away with a clear answer instead of a pile of paperwork to decode. The output is not a diagnosis but a starting point to bring to their provider with informed questions in hand.


## Problem:
Patients looking for clinical trials run into two slow, frustrating walls: eligibility criteria written in dense medical language across public databases, and then, if they find a promising trial, a separate scramble of calling their insurance broker to determine if related visits and procedures would even be covered. Both steps save hours a patient with a serious condition doesn’t need to spend.


## Solution:
This agent allows the patient to describe their condition and situation in simple language. It aligns them with real clinical trial eligibility criteria and then cross-checks the relevant procedures against their insurance plan—instead of one phone call to find a trial and another to ask if they can afford to join it.


## Value: 
Patients get one, fast answer that combines two typically separate burdens – trial eligibility and coverage uncertainty – without having to search for a broker or wade through the raw criteria of ClinicalTrials.gov. It also gives them something concrete and informed to take to their provider, rather than a guess.


## Why:
This problem is not a single lookup, but multi-step reasoning across two different messy domains (clinical eligibility criteria and insurance coverage rules) that have to be cross-referenced against a person’s specific unstructured situation. A static search tool or form can't parse "I have stage 2 type 2 diabetes and my A1C is 8.2" against eligibility criteria written in clinical shorthand, or know which of dozens of plan rules apply. Agents do well because 1) they can take ambiguous, unstructured patient input and map it to structured criteria, 2) the two sub-problems (trial matching and coverage checking) are naturally separable into specialized agents that each do one job well, and 3) a synthesizer agent can reconcile both results into one coherent answer—something a single rigid pipeline would struggle to do cleanly.


## Architecture:
Patient Input -> 

root_coordinator (gemini-2.5-flash) -> 

trial-matching-agent (gemini-2.5-flash) and coverage-checking-agent (gemini-2.5-flash) ->

mcp_server.py and coverage_mcp_server.py -> 

ClinicalTrials.gov API and sample_insurance_plans.jsonn (synthetic data). 

 
## Key Concepts:
  - Agent/multi-agent system
  - MCP server
  - Security features.


## Setup Instructions
1. Clone the repository
2. Create a virtual environment:
```bash
   python3 -m venv .venv
   source .venv/bin/activate
```
3. Install dependencies:
```bash
   pip3 install -r requirements.txt
```
4. Create your `.env` file in the project root:
5. Run the application:
```bash
   python3 -m app.fast_api_app
```
6. Open your browser at `http://localhost:8000`


## Security notes:
- The agent should not store any sensitive patient information. The data should be processed in memory and discarded after each use.
- The agent should not make any decisions that could directly harm the patient. The agent should only provide information that the patient can use to make their own decisions.
- The agent should be transparent about its limitations. The agent should clearly state that it is not a medical professional and that its recommendations are not a substitute for professional medical advice.


## Disclaimer
This tool is for informational purposes only and does not constitute medical, legal, or financial advice. Clinical trial eligibility and insurance coverage determinations should always be confirmed with a qualified healthcare provider and your insurance carrier. Do not make medical decisions based solely on this agent's output.
