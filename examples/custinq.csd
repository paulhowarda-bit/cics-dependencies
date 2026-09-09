*** CUSTINQ - the CICS side of the cross-repository binder contract.
***
*** asm-dependencies parses examples/custinq.asm and reports what that module NEEDS:
*** transaction CINQ, file CUSTMAST, mapsets CUSTSET and CUSTM02, queue CUSTLOG,
*** program CUSTVAL. Its manifest cannot say what any of those names ARE - that is what
*** this deck supplies, and what bind_program_artifacts joins.
***
*** CUSTM02 is deliberately NOT defined here. It is a MAP inside the CUSTSET mapset, not
*** a mapset of its own, so nothing in a CSD ever defines it - and the binder has to leave
*** it unbound with a reason rather than quietly matching it to something.
 DEFINE TRANSACTION(CINQ) GROUP(CUSTG)
 DESCRIPTION(CUSTOMER INQUIRY)
        PROGRAM(CUSTINQ) PROFILE(DFHCICST) TWASIZE(0) STATUS(ENABLED)
 DEFINE PROGRAM(CUSTINQ) GROUP(CUSTG)
        LANGUAGE(ASSEMBLER) DATALOCATION(ANY) EXECKEY(USER) STATUS(ENABLED)
 DEFINE PROGRAM(CUSTVAL) GROUP(CUSTG)
        LANGUAGE(ASSEMBLER) DATALOCATION(ANY) EXECKEY(USER) STATUS(ENABLED)
 DEFINE MAPSET(CUSTSET) GROUP(CUSTG)
        RESIDENT(NO) USAGE(NORMAL) STATUS(ENABLED)
 DEFINE FILE(CUSTMAST) GROUP(CUSTG)
 DESCRIPTION(THE MODULE ONLY READS IT - THE REGION PERMITS UPDATE)
        DSNAME(PROD.CUSTOMER.MASTER) LSRPOOLNUM(1)
        READ(YES) BROWSE(YES) UPDATE(YES) ADD(YES) DELETE(NO)
        JOURNAL(NO) STATUS(ENABLED)
 DEFINE TSMODEL(CUSTLOGM) GROUP(CUSTG)
        PREFIX(CUSTLOG) LOCATION(AUXILIARY) RECOVERY(YES)
 DEFINE LIBRARY(CUSTLIB) GROUP(CUSTG)
        RANKING(50) STATUS(ENABLED) DSNAME01(PROD.CUST.LOADLIB)
 ADD GROUP(CUSTG) LIST(APPLIST)
