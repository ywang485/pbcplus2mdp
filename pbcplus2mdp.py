import sys
import subprocess
import clingo
import mdptoolbox
import numpy as np
import time

# Configuration
fluentPrefix = 'fl_'
actionPrefix = 'act_'
action_project_file_name = 'tmp_action_project.lp'
additional_constraint_file_name = 'tmp_constraint.lp'
state_action_mapping_file_name = 'tmp_state_action_mapping.lp'
predicateArityDivider = '$'

states = {}
actions = {}
transition_probs = None
transition_rwds = None

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

def extractTransitionInfo(answerSets, prop_dict):
	global transition_probs
	global transition_rwds
	transition_probs = np.zeros((len(actions),  len(states), len(states)))
	transition_rwds = np.zeros((len(actions), len(states), len(states)))
	i = 1
	for a in answerSets:
		ss = -1
		es = -1
		act = -1
		for atom in a:
			if atom.name == 'start_state':
				ss = atom.arguments[0].number
			elif atom.name == 'end_state':
				es = atom.arguments[0].number
			elif atom.name == 'action_idx':
				act = atom.arguments[0].number
		transition_probs[act][ss][es] += prop_dict[i]
		transition_rwds[act][ss][es] = extractEndStateAndUtilityFromModel(a)[1]
		i += 1
	# Normalize each column
	for ss in states:
		for act in actions:
			prob_sum = 0.0
			for es in states:
				prob_sum += transition_probs[act][ss][es]
			for es in states:
				transition_probs[act][ss][es] /= prob_sum
				
	return transition_probs, transition_rwds

def extractProbs(rawOutput):
	txt = rawOutput.split('Optimization: ')[-1]
	probabilityTexts = [x.split('\n')[0] for x in txt.split('Probability of Answer ')[1:]]
	prob_dict = np.zeros(len(probabilityTexts) + 1)
	for p in probabilityTexts:
		idx = int(p.split(' ')[0].lstrip('(').rstrip(')'))
		prob = float(p.split(' : ')[1])
		prob_dict[idx] = prob
	return prob_dict

def constructTransitionProbabilitiesAndTransitionReward():
	state_action_definitions = ''
	# Create definition for each transitions
	for s_idx in states:
		state_action_definitions += 'end_state(' + str(s_idx) + ') :- ' + model2conjunction(setTimestep(states[s_idx], 1)) + '.\n'
		state_action_definitions += 'start_state(' + str(s_idx) + ') :- ' + model2conjunction(setTimestep(states[s_idx], 0)) + '.\n'
	for a_idx in range(len(actions)):
		state_action_definitions += 'action_idx(' +str(a_idx)+ ') :- ' + model2conjunction(setTimestep(actions[a_idx], 0)) + '.\n'
	out = open(state_action_mapping_file_name, 'w')
	out.write(state_action_definitions)
	out.close()
	
	# Solve Tr(D, 1) once and collect output
	rawOutput = runLPMLNProgram(program, '-e '+ state_action_mapping_file_name  + ' -all -clingo="-c m=1"')
	print 'Tr(D, 1) solving finished'
	rawAnswerSets = [x.split('\n')[1].lstrip(' ').lstrip('\n').lstrip('\r') for x in rawOutput.split('Answer: ')[1:]]
	answerSets = [getModelFromText(x) for x in rawAnswerSets]
	prob_dict = extractProbs(rawOutput)
	#print prob_dict
	transition_props = extractTransitionInfo(answerSets, prob_dict)
	#print transition_props
	print 'Tranisition Probabilities and Rewards extracted.'
		
# Collect inputs
program = sys.argv[1]
time_horizon = int(sys.argv[2])
discount = float(sys.argv[3])

start_time = time.time()
print 'Action Description in lpmln: ', program
print 'Time Horizon: ', time_horizon
constructStates()
constructActions()
end_time = time.time()
constructTransitionProbabilitiesAndTransitionReward()
#makeTransitionsStochastic()
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
lpmln_solving_time = end_time - start_time
start_time = time.time()
print 'Start solving MDP with mdptoolbox...'
if time_horizon > 0:
	fh = mdptoolbox.mdp.FiniteHorizon(transition_probs, transition_rwds, discount, time_horizon, True)
	fh.run()
else:
	fh = mdptoolbox.mdp.ValueIteration(transition_probs, transition_rwds, discount)
	fh.run()
end_time = time.time()
mdp_solving_time = end_time - start_time
print 'Raw Optimal Policy Output: \n', fh.policy
print 'Optimal Policy: '
if time_horizon > 0:
	for t in range(fh.policy.shape[1]):
		print '-------------------------- Time step ' + str(t) + ' ---------------------------------:'
		for s_idx in range(len(fh.policy)):
			print 'state: ', model2conjunction(states[s_idx])
			print 'action: ', model2conjunction(actions[fh.policy[s_idx][t]])
			print '\n'
else:
	for s_idx in range(len(fh.policy)):
		print 'state: ', model2conjunction(states[s_idx])
		print 'action: ', model2conjunction(actions[fh.policy[s_idx]])
		print '\n'

print 'lpmln solving time: ', lpmln_solving_time
print 'MDP solving time:', mdp_solving_time
