"""Vendor-neutral SIP telephony provider (roadmap Epic 13).

Scaffold only (E13-01): manifest + config schema + a protocol-conformant adapter
stub. The concrete SIP stack (Asterisk ARI / FreeSWITCH ESL, chosen by ADR-0023
in E13-02) is wired in E13-03+. This package must never import
``integrations.telephony_cucm`` or anything Cisco-JTAPI (ADR-0002 §8.17) — an
import-linter contract enforces it.
"""
