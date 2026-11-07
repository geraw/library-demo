import java.io.*;
import java.lang.reflect.*;
import java.net.*;
import java.net.http.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;

/** Adapter only: the fixed scenario source and its selection logic are unchanged. */
public class V011GuidedSuiteHarness {
    static Object field(Object value,String name) throws Exception {
        Field f=value.getClass().getDeclaredField(name); f.setAccessible(true); return f.get(value);
    }
    static String quote(Object value) {
        if(value==null)return "null";
        String s=value.toString(); StringBuilder b=new StringBuilder("\"");
        for(char c:s.toCharArray()) {
            if(c=='"'||c=='\\')b.append('\\').append(c);
            else if(c<32)b.append(String.format("\\u%04x",(int)c)); else b.append(c);
        }
        return b.append('"').toString();
    }
    static volatile int actuatorErrors, listenerErrors;
    static class Monitor extends PrintStream {
        Monitor(PrintStream out){super(out,true);}
        @Override public void println(String s){
            if(s!=null && s.contains("[actuate exception]"))actuatorErrors++;
            if(s!=null && s.contains("[ERROR]"))listenerErrors++;
            super.println(s);
        }
    }
    public static void main(String[] args) throws Exception {
        Class<?> type=Class.forName("StrictGuidedRun");
        Field catalog=type.getDeclaredField("SCENARIOS"); catalog.setAccessible(true);
        List<?> scenarios=(List<?>)catalog.get(null);
        if(args[0].equals("--list")){
            System.out.println("SCENARIO_COUNT="+scenarios.size());return;
        }
        if(args.length>3 && args[3].equals("--smoke")) {
            Class<?> stepType=Class.forName("StrictGuidedRun$Step");
            Constructor<?> makeStep=stepType.getDeclaredConstructor(String.class);makeStep.setAccessible(true);
            Method bind=stepType.getDeclaredMethod("bind",String.class,String.class);bind.setAccessible(true);
            Method require=stepType.getDeclaredMethod("require",String.class,String.class);require.setAccessible(true);
            Object user=makeStep.newInstance("createUser");bind.invoke(user,"reader","id");
            Object book=makeStep.newInstance("createBook");bind.invoke(book,"book","id");
            Object loan=makeStep.newInstance("createLoan");require.invoke(loan,"reader","userId");require.invoke(loan,"book","bookId");
            Class<?> scenarioType=Class.forName("StrictGuidedRun$Scenario");
            Constructor<?> makeScenario=scenarioType.getDeclaredConstructor(String.class,List.class,boolean.class);makeScenario.setAccessible(true);
            scenarios=List.of(makeScenario.newInstance("v011-transport-smoke",List.of(user,book,loan),true));
        }
        System.setOut(new Monitor(System.out)); System.setErr(new Monitor(System.err));
        HttpClient client=HttpClient.newBuilder().connectTimeout(java.time.Duration.ofSeconds(10)).build();
        try(PrintWriter results=new PrintWriter(Files.newBufferedWriter(Path.of(args[1])))){
            int index=0;
            for(Object scenario:scenarios){
                index++; final int caseIndex=index;
                String name=(String)field(scenario,"name"); boolean expected=(boolean)field(scenario,"expectReached");
                int steps=((List<?>)field(scenario,"steps")).size();
                HttpResponse<String> reset=client.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:23243/__campaign__/case"))
                    .timeout(java.time.Duration.ofSeconds(20)).header("Content-Type","application/json")
                    .POST(HttpRequest.BodyPublishers.ofString("{\"case\":"+index+"}")).build(),HttpResponse.BodyHandlers.ofString());
                if(reset.statusCode()!=200)throw new IOException("Case reset failed: "+reset.body());
                actuatorErrors=0;listenerErrors=0;long start=System.nanoTime();
                Method run=type.getDeclaredMethod("runScenario",String.class,scenario.getClass());run.setAccessible(true);
                FutureTask<Object> task=new FutureTask<>(()->run.invoke(null,args[0],scenario));
                Thread thread=new Thread(task,"scenario-"+caseIndex);thread.setDaemon(true);thread.start();
                Object result=null;String error=null;boolean timeout=false;
                try{result=task.get(Integer.parseInt(args[2]),TimeUnit.SECONDS);}
                catch(TimeoutException e){error="CASE_TIMEOUT";timeout=true;}
                catch(Exception e){error=e.toString();if(e.getCause()!=null)error+="; "+e.getCause();}
                boolean reached=result!=null&&(boolean)field(result,"reached");
                boolean pass=result!=null&&reached==expected&&actuatorErrors==0&&listenerErrors==0;
                results.println("{\"case\":"+index+",\"name\":"+quote(name)+",\"steps\":"+steps+
                    ",\"expectReached\":"+expected+",\"reached\":"+reached+",\"reachedSteps\":"+(result==null?0:field(result,"reachedSteps"))+
                    ",\"failedAction\":"+quote(result==null?null:field(result,"failedAction"))+
                    ",\"actuator_errors\":"+actuatorErrors+",\"listener_errors\":"+listenerErrors+
                    ",\"exception\":"+quote(error)+",\"native_pass\":"+pass+",\"wall_seconds\":"+((System.nanoTime()-start)/1e9)+"}");
                results.flush();System.out.println("V011_CASE "+index+"/"+scenarios.size()+" PASS="+pass);
                if(timeout)System.exit(124); // Never reset while an unfinished scenario can still issue requests.
            }
        }
        System.exit(0);
    }
}
