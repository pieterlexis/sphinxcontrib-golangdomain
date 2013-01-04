# -*- coding: utf-8 -*-
"""
    sphinxcontrib.golangdomain
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    The Go language domain.

    :copyright: Copyright 2012 by Yoshifumi YAMAGUCHI
    :license: BSD, see LICENSE for details.
"""

import re
import string

from docutils import nodes
from docutils.parsers.rst import directives

from sphinx import addnodes
from sphinx.roles import XRefRole
from sphinx.locale import l_, _
from sphinx.directives import ObjectDescription
from sphinx.domains import Domain, ObjType, Index
from sphinx.util.compat import Directive
from sphinx.util.nodes import make_refnode
from sphinx.util.docfields import Field, TypedField


# RE to split at word boundaries
wsplit_re = re.compile(r'(\W+)')

# REs for Golang signatures
go_func_sig_re = re.compile(
    r'''^\s* func \s*              # func (ignore)
         (?: \((.*)\) )? \s*       # struct/interface name
         ([\w.]+)                  # thing name
         \( ([\w\s\[\],]*) \) \s*  # arguments
         ([\w\s\[\](),]*) \s* $    # optionally return type
    ''', re.VERBOSE)

go_sig_re = re.compile(
    r'''^(\w+)                     # thing name
    ''', re.VERBOSE)


go_func_split_re = re.compile(
    r'''^\( (.*) \) \s*            # struct/interface name
         ([\w.]+)                  # function name
    ''', re.VERBOSE)


erl_func_sig_re = re.compile(
    r'''^ ([\w.]*:)?             # module name
          (\w+)  \s*             # thing name
          (?: \((.*)\)           # optional: arguments
           (?:\s* -> \s* (.*))?  #           return annotation
          )? $                   # and nothing more
          ''', re.VERBOSE)


class GolangObject(ObjectDescription):
    """
    Description of a Golang language object.
    """

    doc_field_types = [
        TypedField('parameter', label=l_('Parameters'),
                   names=('param', 'parameter', 'arg', 'argument'),
                   typerolename='type', typenames=('type',)),
        Field('returnvalue', label=l_('Returns'), has_arg=False,
              names=('returns', 'return')),
        Field('returntype', label=l_('Return type'), has_arg=False,
              names=('rtype',)),
    ]

    # These Go types aren't described anywhere, so don't try to create
    # a cross-reference to them
    stopwords = set(('const', 'int', 'uint', 'uintptr', 'int8', 'int16', 
                     'int32', 'int64', 'uint8', 'uint16', 'uint32',
                     'uint64', 'string', 'error', '{}interface',
                     '..{}interface'))

    def handle_signature(self, sig, signode):
        m = go_func_sig_re.match(sig)
        if m is not None:
            return self._handle_function_signature(sig, signode, m)

        m = go_sig_re.match(sig)
        if m is not None:
            return self._handle_general_signature(sig, signode, m)
        
    def _handle_general_signature(self, sig, signode, m):
        # determine package name, as well as full name
        # default package is 'builtin'
        env_pkgname = self.options.get(
            'module', self.env.temp_data.get('go:module', 'builtin'))

        name, = m.groups()
        if '.' in name:
            signode += addnodes.desc_name(name, name)
            fullname = name
        else:
            fullname = "%s.%s" % (env_pkgname, name)
            signode += addnodes.desc_name(fullname, fullname)
            
        return fullname

    def _parse_type(self, node, gotype):
        # add cross-ref nodes for all words
        for part in filter(None, wsplit_re.split(gotype)):
            tnode = nodes.Text(part, part)
            if part[0] in string.ascii_letters+'_' and \
                   part not in self.stopwords:
                pnode = addnodes.pending_xref(
                    '', refdomain='go', reftype='type', reftarget=part,
                    modname=None, classname=None)
                pnode += tnode
                node += pnode
            else:
                node += tnode

    def _resolve_package_name(self, signode, struct, name):
        # determine package name, as well as full name
        # default package is 'builtin'
        env_pkgname = self.options.get(
            'module', self.env.temp_data.get('go:module', 'builtin'))

        # debug
        print "\t_resolve_package_name:\n\t%s, %s\n" % (struct, name)

        fullname = ""
        if struct:
            # debug
            print ("\t\t_resolve:\n\t\tstruct = %s\n" % struct)

            signode += addnodes.desc_addname("(", "(")
            try:
                arg, typ = struct.split(' ', 1)
                signode += addnodes.desc_addname(arg+' ', arg+u'\xa0')
            except ValueError:
                typ = struct
            signode += addnodes.desc_name(typ, typ)
            signode += addnodes.desc_addname(") ", ")"+u'\xa0')

            try:
                pkgname, typename = typ.split('.', 1)
                fullname = "(%s.%s) %s" % (pkgname, typename, name)
                signode['module'] = pkgname
            except ValueError:
                fullname = "(%s.%s) %s" % (env_pkgname, typ, name)
                signode['module'] = env_pkgname
        else:
            try:
                pkgname, funcname = name.split('.', 1)
                name = funcname
            except ValueError:
                pkgname = env_pkgname
                funcname = name
            name_prefix = pkgname + '.'
            fullname = "%s.%s" % (pkgname, funcname)
            signode['module'] = pkgname
            signode += addnodes.desc_name(name_prefix, name_prefix)
            # debug
            print "\t\t_resolve:\n\t\t(pkgname, funcname, name, name_prefix) = (%s, %s, %s, %s)\n" % (pkgname, funcname, name, name_prefix)

        signode += addnodes.desc_name(name, name)
        return fullname

    def _handle_function_signature(self, sig, signode, m):
        if m is None:
            raise ValueError
        struct, name, arglist, retann = m.groups()
        # debug
        print ("handle_func:\n(struct, name, arglist, rettype) = ('%s', '%s', '%s', '%s')\n" 
               % (struct, name, arglist, retann))
        signode += addnodes.desc_addname("func ", "func"+u'\xa0')
        fullname = self._resolve_package_name(signode, struct, name)

        if not arglist:
            # for callables, add an empty parameter list
            signode += addnodes.desc_parameterlist()
        else:
            paramlist = addnodes.desc_parameterlist()
            args = arglist.split(",")
            for arg in args:
                arg = arg.strip()
                param = addnodes.desc_parameter('', '', noemph=True)
                try:
                    argname, gotype = arg.split(' ', 1)
                except ValueError:
                    # no argument name given, only the type
                    self._parse_type(param, arg)
                else:
                    param += nodes.emphasis(argname+' ', argname+u'\xa0')
                    self._parse_type(param, gotype)
                    # separate by non-breaking space in the output
                paramlist += param
            signode += paramlist

        if retann:
            signode += addnodes.desc_returns(retann, retann)

        return fullname


    def _get_index_text(self, name):
        if self.objtype == 'function':
            return _('%s (Golang function)') % name
        elif self.objtype == 'variable':
            return _('%s (Golang variable)') % name
        elif self.objtype == 'const':
            return _('%s (Golang const)') % name
        elif self.objtype == 'type':
            return _('%s (Golang type)') % name
        else:
            return ''

    def add_target_and_index(self, name, sig, signode):
        # debug
        print "add_target_and_index:\ndocname = %s\n" % (self.env.docname,)

        if name not in self.state.document.ids:
            signode['names'].append(name)
            signode['ids'].append(name)
            signode['first'] = (not self.names)
            self.state.document.note_explicit_target(signode)

            if self.objtype =='function':
                finv = self.env.domaindata['go']['functions']
                if name in finv:
                    self.env.warn(
                        self.env.docname,
                        'duplicate Golang object description of %s, ' % name +
                        'other instance in ' + self.env.doc2path(finv[name][0]),
                        self.lineno)
                finv[name] = (self.env.docname, self.objtype)
            else:
                oinv = self.env.domaindata['go']['objects']
                if name in oinv:
                    self.env.warn(
                        self.env.docname,
                        'duplicate Golang object description of %s, ' % name +
                        'other instance in ' + self.env.doc2path(oinv[name][0]),
                        self.lineno)
                oinv[name] = (self.env.docname, self.objtype)

        indextext = self._get_index_text(name)
        if indextext:
            self.indexnode['entries'].append(('single', indextext, name, name))


class GolangPackage(Directive):
    """
    Directive to mark description of a new module.
    """

    has_content = False
    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False
    option_spec = {
        'platform': lambda x: x,
        'synopsis': lambda x: x,
        'noindex': directives.flag,
        'deprecated': directives.flag,
    }

    def run(self):
        env = self.state.document.settings.env
        modname = self.arguments[0].strip()
        noindex = 'noindex' in self.options
        env.temp_data['go:module'] = modname
        env.domaindata['go']['modules'][modname] = \
            (env.docname, self.options.get('synopsis', ''),
             self.options.get('platform', ''), 'deprecated' in self.options)
        targetnode = nodes.target('', '', ids=['module-' + modname], ismod=True)
        self.state.document.note_explicit_target(targetnode)
        ret = [targetnode]
        # XXX this behavior of the module directive is a mess...
        if 'platform' in self.options:
            platform = self.options['platform']
            node = nodes.paragraph()
            node += nodes.emphasis('', _('Platforms: '))
            node += nodes.Text(platform, platform)
            ret.append(node)
        # the synopsis isn't printed; in fact, it is only used in the
        # modindex currently
        if not noindex:
            indextext = _('%s (package)') % modname
            inode = addnodes.index(entries=[('single', indextext,
                                             'module-' + modname, modname)])
            ret.append(inode)
        return ret


class GolangCurrentPackage(Directive):
    """
    This directive is just to tell Sphinx that we're documenting
    stuff in module foo, but links to module foo won't lead here.
    """
    has_content = False
    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False
    option_spec = {}

    def run(self):
        env = self.state.document.settings.env
        modname = self.arguments[0].strip()
        if modname == 'None':
            env.temp_data['go:module'] = None
        else:
            env.temp_data['go:module'] = modname
        return []


class GolangXRefRole(XRefRole):
    def process_link(self, env, refnode, has_explicit_title, title, target):
        refnode['go:module'] = env.temp_data.get('go:module')
        if not has_explicit_title:
            title = title.lstrip('.')   # only has a meaning for the target
            target = target.lstrip('~') # only has a meaning for the title
            # if the first character is a tilde, don't display the module/class
            # parts of the contents
            if title[0:1] == '~':
                title = title[1:]
                colon = title.rfind('.')
                if colon != -1:
                    title = title[colon+1:]
        return title, target


class GolangPackageIndex(Index):
    """
    Index subclass to provide the Golang module index.
    """

    name = 'pkgindex'
    localname = l_('Golang Package Index')
    shortname = l_('packages')

    def generate(self, docnames=None):
        content = {}
        # list of prefixes to ignore
        ignores = self.domain.env.config['modindex_common_prefix']
        ignores = sorted(ignores, key=len, reverse=True)
        # list of all modules, sorted by module name
        modules = sorted(self.domain.data['modules'].iteritems(),
                         key=lambda x: x[0].lower())
        # sort out collapsable modules
        prev_modname = ''
        num_toplevels = 0
        for modname, (docname, synopsis, platforms, deprecated) in modules:
            if docnames and docname not in docnames:
                continue

            for ignore in ignores:
                if modname.startswith(ignore):
                    modname = modname[len(ignore):]
                    stripped = ignore
                    break
            else:
                stripped = ''

            # we stripped the whole module name?
            if not modname:
                modname, stripped = stripped, ''

            entries = content.setdefault(modname[0].lower(), [])

            package = modname.split('.')[0]
            if package != modname:
                # it's a submodule
                if prev_modname == package:
                    # first submodule - make parent a group head
                    entries[-1][1] = 1
                elif not prev_modname.startswith(package):
                    # submodule without parent in list, add dummy entry
                    entries.append([stripped + package, 1, '', '', '', '', ''])
                subtype = 2
            else:
                num_toplevels += 1
                subtype = 0

            qualifier = deprecated and _('Deprecated') or ''
            entries.append([stripped + modname, subtype, docname,
                            'module-' + stripped + modname, platforms,
                            qualifier, synopsis])
            prev_modname = modname

        # apply heuristics when to collapse modindex at page load:
        # only collapse if number of toplevel modules is larger than
        # number of submodules
        collapse = len(modules) - num_toplevels < num_toplevels

        # sort by first letter
        content = sorted(content.iteritems())

        return content, collapse


class GolangDomain(Domain):
    """Golang language domain."""
    name = 'go'
    label = 'Golang'
    object_types = {
        'function': ObjType(l_('function'), 'func'),
        'module':   ObjType(l_('module'),   'mod'),    # TODO(ymotongpoo): change to package
        'type':     ObjType(l_('function'), 'type'),
        'var':      ObjType(l_('variable'), 'data'),
        'const':    ObjType(l_('const'),    'data'),
    }

    directives = {
        'function':      GolangObject,
        'type':          GolangObject,
        'var':           GolangObject,
        'const':         GolangObject,
        'module':        GolangPackage,
        'currentmodule': GolangCurrentPackage,
    }
    roles = {
        'func' :  GolangXRefRole(),
        'mod':    GolangXRefRole(),
        'type':   GolangXRefRole(),
        'data':   GolangXRefRole(),
    }
    initial_data = {
        'objects': {},    # fullname -> docname, objtype
        'functions' : {}, # fullname -> targetname, docname
        'modules': {},    # modname -> docname, synopsis, platform, deprecated
    }
    indices = [
        GolangPackageIndex,
    ]

    def clear_doc(self, docname):
        for fullname, (fn, _) in self.data['objects'].items():
            if fn == docname:
                del self.data['objects'][fullname]
        for modname, (fn, _, _, _) in self.data['modules'].items():
            if fn == docname:
                del self.data['modules'][modname]
        for fullname, funcs in self.data['functions'].items():
            if fn == docname:
                del self.data['functions'][fullname]

    def _find_func(self, env, pkgname, name):
        m = go_func_split_re.match(name)
        if m is None:
            if '.' in name:
                fullname = name
            else:
                fullname = "%s.%s" % (pkgname, name)
        else:
            print "%s -> %s\n" % (name, m.groups())
            typename, funcname = m.groups()
            try:
                _, typ = typename.split(' ', 1)
            except ValueError:
                typ = typename
            if '.' in typ:
                fullname = "(%s) %s" % (typ, funcname)
            else:
                fullname = "(%s.%s) %s" % (pkgname, typ, funcname)
        
        # debug
        print "_find_func:\n(fullname, data) = (%s, %s)\n" % (fullname, self.data['functions'])

        return fullname, self.data['functions'][fullname][0]


    def _find_obj(self, env, pkgname, name, typ):
        """Find a Go object for "name", perhaps using the given package.
        Returns a list of (name, object entry) tuples.
        """
        # debug
        print ("_find_obj:\n(env, pkgname, name, typ) = (%s, %s, %s, %s)\n" %
               (env, pkgname, name, typ))

        if typ == 'func':
            return self._find_func(env, pkgname, name)

        if not name:
            return None, None
        if "." not in name:
            name = "%s.%s" % (pkgname, name)

        if name in self.data['objects']:
            return name, self.data['objects'][name][0]
        return None, None


    def resolve_xref(self, env, fromdocname, builder,
                     typ, target, node, contnode):
        if typ == 'mod' and target in self.data['modules']:
            docname, synopsis, platform, deprecated = \
                self.data['modules'].get(target, ('','','', ''))
            if not docname:
                return None
            else:
                title = '%s%s%s' % ((platform and '(%s) ' % platform),
                                    synopsis,
                                    (deprecated and ' (deprecated)' or ''))
                return make_refnode(builder, fromdocname, docname,
                                    'module-' + target, contnode, title)
        else:
            modname = node.get('go:module')
            name, obj = self._find_obj(env, modname, target, typ)
            if not obj:
                return None
            else:
                return make_refnode(builder, fromdocname, obj, name,
                                    contnode, name)

    def get_objects(self):
        for refname, (docname, type) in self.data['objects'].iteritems():
            yield (refname, refname, type, docname, refname, 1)


def setup(app):
    app.add_domain(GolangDomain)
