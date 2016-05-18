===========================
Configuring the application
===========================

The server uses a global configuration :file:`sync.conf` file. Depending on
how your launch the application, the file can be located at:

- :file:`/etc/sync/sync.conf` if you use the :file:`run` module with gunicorn
  or a similar wsgi server.

- :file:`etc/sync.conf` within the directory of the application if you run the
  server using *bin/paster serve development.ini*.

The configuration file has one section for each service provided by the
application.


Storage
=======

The storage section is **storage**. It contains everything neeed by the
storage server to read and write data.

Available options (o: optional, m: multi-line, d: default):

- **backend**: backend used for the storage. Existing backends :
  **sql**, **memcached**.
- **cache_servers** [o, m]: list of memcached servers (host:port)
- **sqluri**: uri for the DB. see RFC-1738 for the format.
  *driver://username:password@host:port/database*. Supported drivers are: sqlite,
  postgres, oracle, mssql, mysql, firebird
- **standard_collections** [o, default: true]: if set to true, the server will
  use hardcoded values for collections.
- **use_quota** [o, default:false]: if set to false, users will not have any quota.
- **quota_size** [o, default:none]: quota size in KB
- **pool_size** [o, default:100]: define the size of the SQL connector pool.
- **pool_recycle** [o, default:3600]: time in ms to recycle a SQL connection that was closed.


Example::

    [storage]

    backend = memcached
    cache_servers = 127.0.0.1:11211
                    192.168.1.13:11211

    sqluri = mysql://sync:sync@localhost/sync
    standard_collections = false
    use_quota = true
    quota_size = 5120
    pool_size = 100
    pool_recycle = 3600



Authentication
==============

The authentication section is **auth**. It contains everything needed for authentication and registration.

Available options (o: optional, m: multi-line, d: default):

- **backend**: backend used for the storage. Existing backends :
  **sql**, **ldap**, **dummy**.
- **ldapuri** [o]: uri for the LDAP server when the ldap backend is used.
- **ldaptimeout** [o, default:-1]: maximum time in secondes allowed for a
  LDAP query. -1 means no timeout.
- **use_tls** [o, default:false]: If set to true, activates TLS when using
  LDAP.
- **bind_user** [o, default:none]: user for common LDAP queries.
- **bind_password** [o, default:none]: password for the bind user.
- **admin_user** [o, default:none]: user with extended rights for write
  operations.
- **admin_password** [o, default:none]: password for the admin user.
- **users_root** [o, default:none]: root for all ldap users. If set to *md5*
  will generate a specific location based on the md5 hash of the
  user name.
- **cache_servers** [o, m]: list of memcached servers (host:port)
- **sqluri**: uri for the DB. see RFC-1738 for the format.
  *driver://username:password@host:port/database*. Supported drivers are: sqlite,
  postgres, oracle, mssql, mysql, firebird
- **pool_size** [o, default:100]: define the size of the SQL connector pool.
- **pool_recycle** [o, default:3600]: time in ms to recycle a SQL connection that was closed.


Example::

    [auth]
    backend = ldap
    ldapuri = ldap://localhost:390
    ldap_timeout =  -1
    use_tls = false

    bind_user = "cn=admin,dc=mozilla"
    bind_password = admin

    admin_user = "cn=admin,dc=mozilla"
    admin_password = admin

    users_root = "ou=users,dc=mozilla"

    sqluri = mysql://sync:sync@localhost/sync
    pool_size = 100
    pool_recycle = 3600

    cache_servers = 127.0.0.1:11211



Captcha
=======

The **captcha** section enables the re-captcha feature during user
registration.

Available options (o: optional, m: multi-line, d: default):

- **use**: if set to false, all operations will be done w/ captcha.
- **public_key**: public key for reCaptacha.
- **private_key**: private key for reCaptacha.
- **use_ssl**: if set to true, will use SSL when connection to recaptcha.

Example::

    [captcha]
    use = true
    public_key = 6Le8OLwSAAAAAK-wkjNPBtHD4Iv50moNFANIalJL
    private_key = 6Le8OLwSAAAAAEKoqfc-DmoF4HNswD7RNdGwxRij
    use_ssl = false


SMTP
====

The **smtp** section configures the SMTP connection used by the application to
send e-mails.

Available options (o: optional, m: multi-line, d: default):

- **host** [o, default:localhost]: SMTP host
- **port** [o, default:25]: SMTP port
- **username** [o, default:none]: SMTP user
- **password** [o, default:none]: SMTP password
- **sender** [o]: E-mail used for the sender field.

Example::

    [smtp]
    host = localhost
    port = 25
    sender = weave@mozilla.com


CEF
===

The **cef** section configues how CEF security alerts are emited.

Available options (o: optional, m: multi-line, d: default):

- **use**: if set to true, CEF alerts are emited.
- **file**: location of the CEF log file. Can be a file path
  or *syslog* to use the syslog facility.
- **syslog.options** [o, default:none]: comma-separated values for syslog.
  Authorized values are: PID, CONS, NDELAY, NOWAIT, PERROR
- **syslog.priority** [o, default:INFO]: priority level.
  Authorized value: EMERG, ALERT, CRIT, ERR, WARNING, NOTICE, INFO, DEBUG.
- **syslog.facility** [o, default:LOCAL4]: facility
  Authorized values: KERN, USER, MAIL, DAEMON, AUTH, LPR, NEWS, UUCP, CRON
  and LOCAL0 to LOCAL7.
- **vendor**: CEF-specific option.
- **version**: CEF-specific option.
- **device_version**: CEF-specific option.
- **product**: CEF-specific option.

Example::

    [cef]
    use = true
    file = syslog

    syslog.options = PID,CONS
    syslog.priority = DEBUG
    syslog.facility = USER

    vendor = mozilla
    version = 0
    device_version = 1.3
    product = weave

