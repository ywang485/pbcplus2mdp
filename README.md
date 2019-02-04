# pbcplus2mdp

A python script that translates probabilistic action descriptions in pBC+ to MDP transition probabilities and rewards, and then use MDPToolBox https://pymdptoolbox.readthedocs.io for planning.

## Usage
$ python pbcplus2mdp.py path/to/lpmln/files time_horizon(0 for infinite) discount_factor(0~1)

For example,
$ python pbcplus2mdp.py block.lpmln 3 0.9

Sample output can be found in examples/blocks.output.

## System Dependencies
This Python script requires the following system to be installed
- clingo python library: https://github.com/potassco/clingo/blob/master/INSTALL.md
- lpmln2asp system: http://reasoning.eas.asu.edu/lpmln/index.html
- MDPToolBox: https://pymdptoolbox.readthedocs.io/en/latest/

## Examples
The folder "examples" contains lpmln encodings for several example pBC+ action description.
- yale.lpmln: A variation of the well-known yale shooting example where there are two (deaf) turkeys: a fat turkey and a slim turkey. Shooting at a turkey may fail to kill the turkey. Normally, shooting at the slim turkey has $0.6$ chance to kill it, and shooting at the fat turkey has 0.9 chance. However, when a turkey is dead, there is 50% chance that the other turkey run away. Killing the fat turkey yields a reward of 8, the slim turkey yields a reward of 10.

- blocks.lpmln: There are two locations L1, L2, and 3 blocks B1, B2, B3 that are originally located at L1. A robot can stack one block on top of another block if the two blocks are at the same location. The robot can also move a block to a different location, resulting in the block being moved as well as all blocks on top of it at the target location, if successful (with probability 0.8). Each moving action has a cost of 1. What is the best way to move all blocks to L2?

- bomb.lpmln: Toilet and bomb example as described in [1]. There are two packages, one of which contains a bomb. The bomb can be defused by dunking the package containing the bomb in the toilet. There is a 0.05 probability of the toilet becoming clogged when a package is placed in it. The goal is to defuse the bomb and not get the toilet clogged.

## References

[1] Younes, Håkan LS, and Michael L. Littman. "PPDDL1. 0: An extension to PDDL for expressing planning domains with probabilistic effects." Techn. Rep. CMU-CS-04-162 (2004).

