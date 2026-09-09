*** LEGACY - a second deck that DISAGREES with appregn.csd, on purpose.
***
*** APMN is defined here too, in a different group, running a different program. This is
*** the two-eras case in its simplest form: parsed together with appregn.csd, both rows
*** stand and a flag names the conflict. Neither wins - a stale deck in a PDS reads
*** exactly like a current one, and only the SIT can settle which is live.
 DEFINE TRANSACTION(APMN) GROUP(OLDG)
 DESCRIPTION(SUPERSEDED - OR IS IT)
        PROGRAM(OLDMENU) TWASIZE(0) STATUS(ENABLED)
 DEFINE PROGRAM(OLDMENU) GROUP(OLDG)
        LANGUAGE(COBOL) STATUS(ENABLED)
 ADD GROUP(OLDG) LIST(OLDLIST)
