import sys
import subprocess
import clingo
import mdptoolbox
import numpy as np

# Configuration
fluentPrefix = 'fl_'
actionPrefix = 'act_'
action_project_file_name = 'tmp_action_project.lp'
additional_constraint_file_name = 'tmp_constraint.lp'
predicateArityDivider = '$'

states = {}
actions = {}
transition_probs = []
transition_rwds = []

def runLPMLNProgram(ipt_file, args):
	cmd = 'lpmln2asp -i' + program + ' ' + args
	try:
		out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
	except Exception, e:
		out = str(e.output)
	return out

def getModelFromText(txt):
	#print txt
	model = []
	answers = txt.lstrip(' ').lstrip('\n').lstrip('\r')
	atoms = answers.split(' ')
	for atom in atoms:
		model.append(clingo.parse_term(atom))
	return model

def extractSpecialAtoms(answer_set, prefix):
	state = []
	for atom in answer_set:
		if atom.name.startswith(prefix):
			state.append(atom)
	return state

def findPredicateNamesWithPrefix(models, prefix):
	found = set([])
	for m in models:
		for atom in m:
			if atom.name.startswith(prefix):
				found.add(atom.name + "$" + str(len(atom.arguments)))
	return found

def createActionProjectFile(actionSet, filename):
	out = open(filename, "w")
	for action in actionSet:
		pred_name = action.split(predicateArityDivider)[0]
		arity = action.split(predicateArityDivider)[1]
		out.write('#show ' + pred_name + '/' + arity + '.\n')
	out.close()

def constructStates():
	rawOutput = runLPMLNProgram(program, '-all -clingo="-c m=0"')
	if 'UNSATISFIABLE' in rawOutput or "UNKNOWN" in rawOutput:
		print 'No state found. Exiting...'
		exit()
	rawAnswerSets = [x.split('\n')[1].lstrip(' ').lstrip('\n').lstrip('\r') for x in rawOutput.split('Answer: ')[1:]]
	answerSets = [getModelFromText(x) for x in rawAnswerSets]
	state_descs = [extractSpecialAtoms(x, fluentPrefix) for x in answerSets]
	i = 0
	for desc in state_descs:
		states[i] = desc
		i += 1

def constructActions():
	rawOutput = runLPMLNProgram(program, '-all -clingo="-c m=1"')
	if 'UNSATISFIABLE' in rawOutput or "UNKNOWN" in rawOutput:
		print 'No action found. Exiting...'
		exit()
	rawAnswerSets = [x.split('\n')[1].lstrip(' ').lstrip('\n').lstrip('\r') for x in rawOutput.split('Answer: ')[1:]]
	answerSets = [getModelFromText(x) for x in rawAnswerSets]
	action_predicates = findPredicateNamesWithPrefix(answerSets, actionPrefix)
	createActionProjectFile(action_predicates, action_project_file_name)
	rawOutput = runLPMLNProgram(program, '-e '+ action_project_file_name + ' -all -clingo="-c m=1 --project"')
	rawAnswerSets = [x.split('\n')[1].lstrip(' ').lstrip('\n').lstrip('\r') for x in rawOutput.split('Answer: ')[1:]]
	answerSets = [getModelFromText(x) for x in rawAnswerSets]
	action_descs = [extractSpecialAtoms(x, actionPrefix) for x in answerSets]
	i = 0
	for desc in action_descs:
		actions[i] = desc
		i += 1

def model2constraints(model):
	constraint = ''
	for atom in model:
		constraint += ':- not ' + str(atom) + '.\n'
	return constraint

def model2conjunction(model):
	return ','.join([str(x) for x in model])

def setTimestep(model, timestep):
	new_model = []
	for atom in model:
		new_atom = clingo.Function(atom.name, atom.arguments[:-1] + [clingo.Number(timestep)])
		new_model.append(new_atom)
	return new_model

def extractEndStateProbabilitiesFromRawOutput(txt):
	txt = txt.split('Optimization: ')[-1]
	probabilityTexts = [x.split('\n')[0] for x in txt.split('end_state')[1:]]
	result = {}
	for p in probabilityTexts:
		s_idx = int(p.split(' ')[0].lstrip('(').rstrip(')'))
		prob = float(p.split(' ')[1])
		result[s_idx] = prob
	return result

def extractEndStateAndUtilityFromModel(model):
	utility = 0
	end_state = -1
	for atom in model:
		if atom.name == 'utility':
			utility += atom.arguments[0].number
		if atom.name == 'end_state':
			end_state = atom.arguments[0]
	return end_state, utility

def makeTransitionsStochastic():
	for a in transition_probs:
		for s in a:
			for i in range(len(s)-1, -1, -1):
				if s[i] != 0:
					s[i] = 1 - sum(s[:i])
					break

def constructTransitionProbabilitiesAndTransitionReward():
	state_definitions = ''
	# Create definition for each state at timestep 1
	for s_idx in states:
		state_definitions += 'end_state(' + str(s_idx) + ') :- ' + model2conjunction(setTimestep(states[s_idx], 1)) + '.\n'

	for a_idx in range(len(actions)):
		transition_probs.append([])
		transition_rwds.append([])
		for s_idx in range(len(states)):
			out = open(additional_constraint_file_name, 'w')
			out.write(state_definitions)
			out.write(model2constraints(states[s_idx]))
			out.write(model2constraints(actions[a_idx]))
			out.close()
			rawOutput = runLPMLNProgram(program, '-e '+ additional_constraint_file_name  + ' -all -q end_state -clingo="-c m=1"')
			rawAnswerSets = [x.split('\n')[1].lstrip(' ').lstrip('\n').lstrip('\r') for x in rawOutput.split('Answer: ')[1:]]
			answerSets = [getModelFromText(x) for x in rawAnswerSets]
			probs = extractEndStateProbabilitiesFromRawOutput(rawOutput)
			transition_probs[-1].append([0] * len(states))
			transition_rwds[-1].append([0] * len(states))
			for a in answerSets:
				s, u = extractEndStateAndUtilityFromModel(a)
				transition_rwds[-1][-1][s.number] = u
			for p in probs:
				transition_probs[-1][-1][p] = probs[p]
		

# Collect inputs
program = sys.argv[1]
time_horizon = int(sys.argv[2])

print 'Action Description in lpmln: ', program
print 'Time Horizon: ', time_horizon
constructStates()
constructActions()
constructTransitionProbabilitiesAndTransitionReward()
transition_probs = np.array(transition_probs)
transition_rwds = np.array(transition_rwds)
makeTransitionsStochastic()
print str(len(states)) + ' states detected.'
print str(len(actions)) + ' actions detected.'
print 'Transition Probabilitities: '
for a_idx in actions:
	print 'action ' + str(a_idx), model2conjunction(actions[a_idx])
	print transition_probs[a_idx]
print 'Transition Rewards: '
for a_idx in actions:
	print 'action ' + str(a_idx), model2conjunction(actions[a_idx])
	print transition_rwds[a_idx]
fh = mdptoolbox.mdp.FiniteHorizon(transition_probs, transition_rwds, 1, time_horizon, True)
fh.run()
print 'Optimzal Policy: ', fh.policy


