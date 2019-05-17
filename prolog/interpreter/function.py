import random

from prolog.interpreter.term import Callable, Atom, Var, NumberedVar, BindingVar
from prolog.interpreter.memo import EnumerationMemo
from prolog.interpreter.signature import Signature
from rpython.rlib import jit, objectmodel, unroll
from prolog.interpreter.error import UnificationFailed
from prolog.interpreter.helper import is_callable
from prolog.interpreter.term import specialized_term_classes
# XXX needs tests

cutsig = Signature.getsignature("!", 0)
prefixsig = Signature.getsignature(":", 2)



class Rule(object):
    _immutable_ = True
    _immutable_fields_ = ["headargs[*]", "groundargs[*]"]
    _attrs_ = ['next', 'head', 'headargs', 'groundargs', 'contains_cut',
               'body', 'env_size_shared', 'env_size_body', 'env_size_head',
               'signature', 'module', 'file_name',
               'line_range', 'source', 'scores', 'expanded']
    unrolling_attrs = unroll.unrolling_iterable(_attrs_)


    def __init__(self, head, body, module, next = None):
        from prolog.interpreter import helper
        head = head.dereference(None)
        assert isinstance(head, Callable)
        memo = EnumerationMemo()
        self.head = h = head.enumerate_vars(memo)
        memo.in_head = False
        if h.argument_count() > 0:
            self.headargs = h.arguments()
            # an argument is ground if enumeration left it unchanged, because
            # that means it contains no variables
            self.groundargs = [h.argument_at(i) is head.argument_at(i)
                    for i in range(h.argument_count())]
        else:
            self.headargs = None
            self.groundargs = None
        if body is not None:
            body = body.dereference(None)
            body = helper.ensure_callable(body)
            self.body = body.enumerate_vars(memo)
        else:
            self.body = None
        memo.assign_numbers()
        self.env_size_body = memo.nbody
        self.env_size_head = memo.nhead
        self.env_size_shared = memo.nshared
        self.signature = head.signature()
        self.module = module
        self.next = next
        self.file_name = "<unknown>"
        self.line_range = None
        self.source = None
        self.scores = None
        self.expanded = False

        self._does_contain_cut()


    def _init_source_info(self, tree, source_info):
        from rpython.rlib.parsing.tree import Nonterminal, Symbol
        start_source_pos = tree.getsourcepos()
        end_source_pos = None
        parts = [tree]
        while parts:
            first = parts.pop()
            if isinstance(first, Nonterminal):
                parts.extend(first.children)
            else:
                assert isinstance(first, Symbol)
                end_source_pos = first.getsourcepos()
                break
        if end_source_pos is None:
            end_source_pos = start_source_pos
        self.line_range = [start_source_pos.lineno, end_source_pos.lineno + 1]
        start = start_source_pos.i
        stop = end_source_pos.i + 1
        assert 0 <= start <= stop
        self.source = source_info[start:stop]

    def _does_contain_cut(self):
        if self.body is None:
            self.contains_cut = False
            return
        stack = [self.body]
        while stack:
            current = stack.pop()
            if isinstance(current, Callable):
                if current.signature().eq(cutsig):
                    self.contains_cut = True
                    return
                else:
                    stack.extend(current.arguments())
        self.contains_cut = False

    def build_query(self, arglist):
        jit.promote(self)
        return Callable.build(self.signature.name, arglist,
                              signature=self.signature)


    @jit.unroll_safe
    def clone_body_from_rulecont(self, heap, rulecont):
        body = self.body
        if body is None:
            return None
        body_env = [None] * self.env_size_body
        for i in range(self.env_size_shared):
            body_env[i] = rulecont._get_list(i)
        return body.copy_standardize_apart(heap, body_env)[0]


    @jit.unroll_safe
    def clone_and_unify_head(self, heap, head):
        env = self.unify_and_standardize_apart_head(heap, head)
        body = self.body
        if body is None:
            return None
        body_env = [None] * self.env_size_body
        for i in range(self.env_size_shared):
            body_env[i] = env[i]
        return body.copy_standardize_apart(heap, body_env)[0]

    @jit.unroll_safe
    def unify_and_standardize_apart_head(self, heap, head, similarity=None):
        env = [None] * self.env_size_head
        #i = similarity.query_idx
        i = 0
        heap.score = similarity.tnorm(self.scores[i], heap.score)
        if heap.score < similarity.threshold:
            raise UnificationFailed
        if self.headargs is not None:
            assert isinstance(head, Callable)
            for i in range(len(self.headargs)):
                arg2 = self.headargs[i]
                arg1 = head.argument_at(i)
                if self.groundargs[i]:
                    arg2.unify(arg1, heap, similarity=similarity)
                else:
                    arg2.unify_and_standardize_apart(arg1, heap, env)
        shared_env = [None] * self.env_size_body
        for i in range(self.env_size_shared):
            shared_env[i] = env[i]
        return shared_env

    def __repr__(self):
        if self.body is None:
            return "%s." % (self.head, )
        return "%s :- %s." % (self.head, self.body)

    def instance_copy(self):
        other = objectmodel.instantiate(Rule)
        for f in Rule.unrolling_attrs:
            setattr(other, f, getattr(self, f))
        return other
        
    def copy(self, stopat=None):
        first = self.instance_copy()
        curr = self.next
        copy = first
        while curr is not stopat:
            # if this is None, the stopat arg was invalid
            assert curr is not None
            new = curr.instance_copy()
            copy.next = new
            copy = new
            curr = curr.next
        return first, copy

    @jit.unroll_safe
    def find_applicable_rule(self, query, similarity=None):
        # This method should do some quick filtering on the rules to filter out
        # those that cannot match query. Here is where e.g. indexing should
        # occur.
        while self is not None:
            if self.headargs is not None:
                assert isinstance(query, Callable)
                for i in range(len(self.headargs)):
                    arg2 = self.headargs[i]
                    arg1 = query.argument_at(i)
                    if not arg2.quick_unify_check(arg1, similarity=similarity):
                        break
                else:
                    return self
            else:
                return self
            self = self.next
        return None

    def find_next_applicable_rule(self, query, similarity=None):
        if self.next is None:
            return None
        return self.next.find_applicable_rule(query, similarity=similarity)
    
    def __eq__(self, other):
        return self.__class__ == other.__class__ and self.__dict__ == other.__dict__
    def __ne__(self, other):
        return not self == other

def _make_toplevel_rule(module):
    # this is a rule object that is used for error messages when running
    # toplevel goals
    head = Callable.build("<%s toplevel>" % (module.name, ))
    return Rule(head, None, module)

class Function(object):
    _immutable_fields_ = ["rulechain?", "meta_args?"]
    def __init__(self):
        self.meta_args = None
        self.rulechain = self.last = None

    def __iter__(self):
        rule = self.rulechain
        while rule is not None:
            yield rule
            rule = rule.next

    @jit.unroll_safe
    def add_meta_prefixes(self, query, current_module):
        if not self.meta_args:
            return query
        numargs = query.argument_count()
        args = [None] * numargs
        for i in range(numargs):
            args[i] = self._prefix_argument(query.argument_at(i),
                    self.meta_args[i], current_module)
        return Callable.build(query.name(), args)

    def _prefix_argument(self, arg, meta_arg, module):
        if meta_arg in "0123456789:":
            if not (isinstance(arg, Callable) and arg.signature().eq(prefixsig)):
                return Callable.build(":", [module, arg])
        return arg

    def add_rule(self, rule, atend):
        if self.rulechain is None:
            self.rulechain = self.last = rule
        elif atend:
            self.rulechain, last = self.rulechain.copy()
            self.last = rule
            last.next = self.last
        else:
            rule.next = self.rulechain
            self.rulechain = rule


    def remove(self, rulechain):
        self.rulechain, last = self.rulechain.copy(rulechain)
        last.next = rulechain.next

