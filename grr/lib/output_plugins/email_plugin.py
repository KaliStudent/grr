#!/usr/bin/env python
"""Email live output plugin."""



import cgi
import urllib

from grr import config
from grr.lib import aff4
from grr.lib import email_alerts
from grr.lib import output_plugin
from grr.lib import utils
from grr.lib.rdfvalues import standard
from grr.lib.rdfvalues import structs as rdf_structs
from grr.proto import output_plugin_pb2


class EmailOutputPluginArgs(rdf_structs.RDFProtoStruct):
  protobuf = output_plugin_pb2.EmailOutputPluginArgs
  rdf_deps = [
      standard.DomainEmailAddress,
  ]


class EmailOutputPlugin(output_plugin.OutputPlugin):
  """An output plugin that sends an email for each response received."""

  name = "email"
  description = "Send an email for each result."
  args_type = EmailOutputPluginArgs
  produces_output_streams = False

  template = """
<html><body><h1>GRR got a new result in %(source_urn)s.</h1>

<p>
  Grr just got a response in %(source_urn)s from client %(client_id)s
  (%(hostname)s).<br />
  <br />
  Click <a href='%(admin_ui_url)s/#%(client_fragment_id)s'> here </a> to
  access this machine. <br />
  This notification was created by %(creator)s.
</p>
%(additional_message)s
<p>Thanks,</p>
<p>%(signature)s</p>
</body></html>"""

  too_many_mails_msg = ("<p> This hunt has now produced %d results so the "
                        "sending of emails will be disabled now. </p>")

  def InitializeState(self):
    super(EmailOutputPlugin, self).InitializeState()
    self.state.emails_sent = 0

  @utils.Synchronized
  def IncrementCounter(self):
    self.state.emails_sent += 1
    return self.state.args.emails_limit - self.state.emails_sent

  def ProcessResponse(self, response):
    """Sends an email for each response."""
    emails_left = self.IncrementCounter()
    if emails_left < 0:
      return

    client_id = response.source
    client = aff4.FACTORY.Open(client_id, token=self.token)
    hostname = client.Get(client.Schema.HOSTNAME) or "unknown hostname"
    client_fragment_id = urllib.urlencode((("c", client_id),
                                           ("main", "HostInformation")))

    if emails_left == 0:
      additional_message = (
          self.too_many_mails_msg % self.state.args.emails_limit)
    else:
      additional_message = ""

    subject = ("GRR got a new result in %s." % self.state.source_urn)

    template_args = dict(
        client_id=client_id,
        client_fragment_id=client_fragment_id,
        admin_ui_url=config.CONFIG["AdminUI.url"],
        source_urn=self.state.source_urn,
        additional_message=additional_message,
        signature=config.CONFIG["Email.signature"],

        # Values that have to be escaped.
        hostname=cgi.escape(utils.SmartStr(hostname)),
        creator=cgi.escape(utils.SmartStr(self.token.username)))

    email_alerts.EMAIL_ALERTER.SendEmail(
        self.state.args.email_address,
        "grr-noreply",
        subject,
        self.template % template_args,
        is_html=True)

  def ProcessResponses(self, responses):
    for response in responses:
      self.ProcessResponse(response)
