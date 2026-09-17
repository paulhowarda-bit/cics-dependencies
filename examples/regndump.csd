 DFHCSDUP - CICS DEFINITION FILE UTILITY PROGRAM                          15.206 23:09
 LIST GROUP(RPTG) OBJECTS
 FILE(RPTFILE)           GROUP(RPTG)                                                       15.206 23:09
                         DESCRIPTION(REPORTING EXTRACT FILE)
                         DSNAME(PROD.RPT.EXTRACT)
                         RLSACCESS(NO)          LSRPOOLNUM(1)        READINTEG(UNCOMMITTED)
                         DSNSHARING(ALLREQS)    STRINGS(1)           NSRGROUP()
                         REMOTESYSTEM()         REMOTENAME()
                         ADD(YES)               BROWSE(YES)          DELETE(NO)
                         READ(YES)              UPDATE(YES)          STATUS(ENABLED)
                         DEFINETIME(15/07/25 23:09:21)
                         CHANGETIME(15/07/25 23:09:21)
 TRANSACTION(RPTA)       GROUP(RPTG)                                                       15.206 23:09
                         DESCRIPTION(REPORT ENQUIRY)
                         PROGRAM(RPTMAIN)       TWASIZE(0)           PROFILE(DFHCICST)
                         TASKDATALOC(ANY)       TASKDATAKEY(USER)    STATUS(ENABLED)
                         ROUTABLE(NO)           REMOTESYSTEM(RSYB)   REMOTENAME(RPTB)
                         DEFINETIME(15/07/25 23:09:21)
                         CHANGETIME(15/07/25 23:09:21)
 PROGRAM(RPTMAIN)        GROUP(RPTG)                                                       15.206 23:09
                         DESCRIPTION(REPORT DRIVER)
                         LANGUAGE(COBOL)        DATALOCATION(ANY)    EXECKEY(USER)
                         CONCURRENCY(QUASIRENT) STATUS(ENABLED)
                         DEFINETIME(15/07/25 23:09:21)
                         CHANGETIME(15/07/25 23:09:21)
-
 DFH5123 I PRIMARY CSD CLOSED; DDNAME: DFHCSD   DSNAME: PROD.CICS.RPTA.DFHCSD
 DFH5107 I COMMANDS EXECUTED SUCCESSFULLY:    1
 DFH5109 I END OF DFHCSDUP UTILITY JOB.  HIGHEST RETURN CODE WAS:   0
 DFHCSDUP - CICS DEFINITION FILE UTILITY PROGRAM                          15.206 23:11
 LIST GROUP(RPTG2) OBJECTS
 MAPSET(RPTSET)          GROUP(RPTG2)                                                      15.206 23:11
                         DESCRIPTION(REPORT MAPS)
                         RESIDENT(NO)           USAGE(NORMAL)        STATUS(ENABLED)
                         DEFINETIME(15/07/25 23:11:04)
                         CHANGETIME(15/07/25 23:11:04)
 DFH5123 I PRIMARY CSD CLOSED; DDNAME: DFHCSD   DSNAME: PROD.CICS.RPTA.DFHCSD
 DFH5107 I COMMANDS EXECUTED SUCCESSFULLY:    1
 DFH5109 I END OF DFHCSDUP UTILITY JOB.  HIGHEST RETURN CODE WAS:   0
