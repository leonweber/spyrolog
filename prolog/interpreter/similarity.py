from prolog.interpreter.term import Atom, NumberedVar
from prolog.interpreter.memo import EnumerationMemo
from rpython.rlib.objectmodel import specialize


def get_similarity_from_file(path, lambda_cut, entity_tnorm, predicate_tnorm):
    similarity = Similarity(lambda_cut, entity_tnorm, predicate_tnorm)
    with open(path) as f:
        text = f.read()
        for line in text.split('\n'):
            split = line.split('=')
            if len(split) < 2:
                continue
            split2 = split[0].split('~')
            similarity.set_score(split2[0].strip(), split2[1].strip(), float(split[1].strip()))

    return similarity

def ruleterm_to_key(ruleterm):
    memo = EnumerationMemo()
    term = ruleterm.enumerate_vars(memo)
    memo.assign_numbers()

    return term_to_key(term)

def term_to_key(term):
    if isinstance(term, Atom):
       return term.name()
    elif isinstance(term, NumberedVar):
        return 'var' + str(term.num)
    else:
        result = term.signature().name
        for arg in term.arguments():
            result += term_to_key(arg)
        return result


class Similarity(object):
    def __init__(self, threshold, entity_tnorm='prod', predicate_tnorm='prod'):
        self._table = {}
        self._domain = {}
        self.lambda_cut = threshold
        self.threshold = threshold
        self.entity_tnorm_name = entity_tnorm
        self.predicate_tnorm_name = predicate_tnorm
        self.rule_scores = {}
        self.query_idx = 0

    def _get_key(self, name1, name2):
        if name1 > name2:
            key = (name1, name2)
        else:
            key = (name2, name1)

        return key

    def parse_rulescores(self, text, engine):
        rules = []
        for line in text.split('\n'):
            split3 = line.split('=')
            if len(split3) < 2:
                continue
            rule = split3[0].strip()
            rules.append(rule)
            scores = []
            for score in split3[1].split('|'):
                scores.append(float(score))
            parse = engine.parse(rule)[0][0]
            ruleterm = engine._term_expand(parse)
            key = ruleterm_to_key(ruleterm)
            self.rule_scores[key] = scores

        engine.runstring("\n".join(rules), similarity=self)

    def get_score(self, name1, name2):
        if name1 == name2:
            return 1.0
        else:
            return self._table.get(self._get_key(name1, name2), 0)

    def get_score_signatures(self, signature1, signature2):
        if signature1.numargs != signature2.numargs:
            return 0
        else:
            return self.get_score(signature1.name, signature2.name)

    def get_initial_rule_scores(self, ruleterm):
        key = ruleterm_to_key(ruleterm)
        if key not in self.rule_scores:
            print "Could not find ", key
        return self.rule_scores[key]

    def set_score(self, name1, name2, score):
        self._domain[name1] = None
        self._domain[name2] = None
        self._table[self._get_key(name1, name2)] = score

    def get_similar(self, name):
        similar = []
        for other in self._domain.keys():
            score = self.get_score(name, other)
            if score >= self.threshold:
                similar.append((other, score))
        return similar

    def reset_threshold(self):
        self.threshold = self.lambda_cut

    def function_tnorm(self, a, b):
        return self.tnorm(a,b, self.predicate_tnorm_name)

    def term_tnorm(self, a, b):
        return self.tnorm(a,b, self.entity_tnorm_name)

    def tnorm(self, a, b, name):
        if name == 'prod':
            return a*b
        elif name == 'luk':
            return max(0, a+b-1)
        elif name == 'min':
            return min(a, b)
        else:
            raise ValueError("Invalid t-norm " + name)

