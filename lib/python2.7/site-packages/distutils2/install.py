import logging
from distutils2.index import wrapper
from distutils2.index.errors import ProjectNotFound, ReleaseNotFound
from distutils2.depgraph import generate_graph
from distutils2._backport.pkgutil import get_distributions


"""Provides the installation script.

The goal of this script is to install a release from the indexes (eg.
PyPI), including the dependencies of the releases if needed.

It uses the work made in pkgutil and by the index crawlers to browse the
installed distributions, and rely on the instalation command to install.

Please note that this installation *script* iis different of the installation
*command*. While the command only install one distribution, the script installs
all the dependencies from a distribution, in a secure way.
"""


class InstallationException(Exception):
    pass


def _update_infos(infos, new_infos):
    """extends the lists contained in the `info` dict with those contained
    in the `new_info` one
    """
    for key, value in infos.items():
        if key in new_infos:
            infos[key].extend(new_infos[key])


def get_infos(requirements, index=None, installed=None,
                     prefer_final=True):
    """Return the informations on what's going to be installed and upgraded.

    :param requirements: is a *string* containing the requirements for this
                         project (for instance "FooBar 1.1" or "BarBaz (<1.2)")
    :param index: If an index is specified, use this one, otherwise, use
                  :class index.ClientWrapper: to get project metadatas.
    :param installed: a list of already installed distributions.
    :param prefer_final: when picking up the releases, prefer a "final" one
                         over a beta/alpha/etc one.

    The results are returned in a dict, containing all the operations
    needed to install the given requirements::

        >>> get_install_info("FooBar (<=1.2)")
        {'install': [<FooBar 1.1>], 'remove': [], 'conflict': []}

    Conflict contains all the conflicting distributions, if there is a
    conflict.
    """

    if not index:
        index = wrapper.ClientWrapper()

    if not installed:
        installed = get_distributions()

    # Get all the releases that match the requirements
    try:
        releases = index.get_releases(requirements)
    except (ReleaseNotFound, ProjectNotFound), e:
        raise InstallationException('Release not found: "%s"' % requirements)

    # Pick up a release, and try to get the dependency tree
    release = releases.get_last(requirements, prefer_final=prefer_final)

    # Iter since we found something without conflicts
    metadata = release.fetch_metadata()

    # Get the distributions already_installed on the system
    # and add the one we want to install

    distributions = installed + [release]
    depgraph = generate_graph(distributions)

    # Store all the already_installed packages in a list, in case of rollback.
    infos = {'install': [], 'remove': [], 'conflict': []}

    # Get what the missing deps are
    for dists in depgraph.missing.values():
        if dists:
            logging.info("missing dependencies found, installing them")
            # we have missing deps
            for dist in dists:
                _update_infos(infos,
                             get_infos(dist, index, installed))

    # Fill in the infos
    existing = [d for d in installed if d.name == release.name]
    if existing:
        infos['remove'].append(existing[0])
        infos['conflict'].extend(depgraph.reverse_list[existing[0]])
    infos['install'].append(release)
    return infos
